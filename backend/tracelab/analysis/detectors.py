import asyncio
import hashlib
import marshal

from tracelab.analysis.models import AnalysisSignal, DetectorDefinition
from tracelab.analysis.projection import signals
from tracelab.analysis.rules import modification, rule_matches, signature
from tracelab.analysis.semantic import semantic_events
from tracelab.analysis.statistical import features, statistical_matches
from tracelab.classifiers.runner import canonical_hash
from tracelab.models.domain import now
from tracelab.presentation import VERSION, research_events


class LLMDetectorAdapter:
    detector_type = "llm"

    def __init__(self, service):
        self.service = service

    async def run(self, trajectory_ids, config):
        # Execution stays in the existing bounded classifier job runner.
        return [
            AnalysisSignal.model_validate(s)
            for tid in trajectory_ids
            for s in signals(self.service.db, tid)
            if s["sourceType"] == "llm"
        ]


class RuleDetector:
    detector_type = "rule"

    def __init__(self, service):
        self.service = service

    async def run(self, trajectory_ids, config):
        definition = DetectorDefinition.model_validate(config)
        output = []
        for tid in trajectory_ids:
            events = research_events(
                await self.service.load_events(tid),
                bool(definition.parameters.get("includeRuntime", False)),
            )

            def calculate():
                if self.detector_type == "rule":
                    return list(rule_matches(events, definition.parameters))
                return list(
                    statistical_matches(events, semantic_events(events), definition.parameters)
                )

            matches = await asyncio.to_thread(calculate)
            if self.detector_type == "rule" and not matches and events:
                matches = [
                    {
                        "start": events[0]["index"],
                        "end": events[-1]["index"],
                        "score": 0.0,
                        "label": "no_matches",
                        "evidence": [],
                        "details": {
                            "matchCount": 0,
                            "evaluatedEvents": len(events),
                            "outputLabel": definition.parameters.get("label", "rule_match"),
                            "interpretation": "Completed rule evaluation found no matches; this is not evidence that the underlying behavior is absent.",
                        },
                    }
                ]
            input_hash = canonical_hash(events)
            manifest_id = f"{tid}:{input_hash}"
            self.service.db.put(
                "analysis_inputs",
                {
                    "id": manifest_id,
                    "trajectoryId": tid,
                    "inputHash": input_hash,
                    "inputEventIds": [e["id"] for e in events],
                },
            )
            for match in matches:
                output.append(
                    AnalysisSignal(
                        trajectory_id=tid,
                        name=definition.name
                        if self.detector_type == "rule"
                        else match["label"].replace("_", " "),
                        source_type=self.detector_type,
                        channel="GRAY_BOX"
                        if definition.parameters.get("operation") in ("sensitive", "modification")
                        else "BLACK_BOX",
                        start_event_index=match["start"],
                        end_event_index=match["end"],
                        score=match["score"],
                        label=match["label"],
                        evidence_event_ids=match["evidence"],
                        provenance={
                            "definition": definition.wire(),
                            "detectorId": definition.id,
                            "version": definition.version,
                            "parameters": definition.parameters,
                            "inputTrajectoryIds": trajectory_ids,
                            "inputManifestId": manifest_id,
                            "windowEventIds": match["evidence"],
                            "inputHash": input_hash,
                            "implementationVersion": "tracelab-analysis-2",
                            "presentationVersion": VERSION,
                            "eventBasis": "recorded"
                            if definition.parameters.get("includeRuntime")
                            else "research",
                            "implementationHash": hashlib.sha256(
                                b"".join(
                                    marshal.dumps(function.__code__)
                                    for function in (
                                        (rule_matches, modification, signature)
                                        if self.detector_type == "rule"
                                        else (
                                            statistical_matches,
                                            features,
                                            signature,
                                            semantic_events,
                                        )
                                    )
                                )
                            ).hexdigest(),
                            "implementationHashKind": "python-code-objects",
                            "createdAt": now(),
                            "rawResult": match,
                        },
                        metadata={
                            **match["details"],
                            "laneId": definition.id
                            + ":"
                            + match["details"].get("outputLabel", match["label"]),
                            "heuristic": True,
                        },
                    )
                )
        return output


class StatisticalDetector(RuleDetector):
    detector_type = "statistical"
