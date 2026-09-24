"""Additive analysis API; all inputs are canonical, source-independent records."""

import asyncio

from tracelab.analysis.contrastive import ContrastiveDetector, compare
from tracelab.analysis.detectors import RuleDetector, StatisticalDetector
from tracelab.analysis.models import (
    AnalysisSignal,
    ArtifactRef,
    DetectorDefinition,
    ModelInternalSource,
    OutlineNode,
)
from tracelab.analysis.outline import build_outline
from tracelab.analysis.projection import capabilities, signal_summaries, signals
from tracelab.analysis.relationships import relationships
from tracelab.analysis.rules import BUILTINS
from tracelab.analysis.semantic import coordinates, semantic_events
from tracelab.classifiers.runner import canonical_hash
from tracelab.models.domain import Job, uid
from tracelab.presentation import VERSION
from tracelab.presentation.storage import counts

METHODS = {
    "analysis.overview",
    "analysis.signals",
    "analysis.signal",
    "analysis.definitions",
    "analysis.save",
    "analysis.run",
    "analysis.compare",
    "analysis.pairs",
    "analysis.matchCandidates",
    "analysis.artifact",
    "analysis.importSignals",
    "analysis.importParquet",
    "analysis.interpret",
}


async def handle(service, method, p):
    db = service.db
    if method == "analysis.definitions":
        return {"definitions": db.list("detector_definitions"), "templates": BUILTINS}
    if method == "analysis.save":
        item = DetectorDefinition.model_validate(p)
        old = db.maybe("detector_definitions", item.id)
        if old and old != item.wire():
            item.previous_id, item.id, item.version = item.id, uid("detector"), old["version"] + 1
        return db.put("detector_definitions", item)
    if method == "analysis.run":
        definition = DetectorDefinition.model_validate(
            db.get("detector_definitions", p["definitionId"])
        )
        ids = list(dict.fromkeys(p["trajectoryIds"]))
        if not ids:
            raise ValueError("Select at least one trajectory")

        async def run(job):
            detector = {
                "rule": RuleDetector,
                "statistical": StatisticalDetector,
                "contrastive": ContrastiveDetector,
            }[definition.detector_type](service)
            groups = [ids] if definition.detector_type == "contrastive" else [[tid] for tid in ids]
            for group in groups:
                found = await detector.run(group, definition.wire())
                for item in found:
                    item.provenance["jobId"] = job.id
                db.put_many("analysis_signals", found)
                job.completed += len(group)
                service.jobs.save(job)
                await asyncio.sleep(0)

        return service.jobs.start(
            Job(
                kind="analysis",
                name=definition.name,
                total=len(ids),
                metadata={"definition": definition.wire(), "trajectoryIds": ids},
            ),
            run,
        )
    if method == "analysis.signals":
        return await asyncio.to_thread(signal_summaries, db, p["trajectoryId"])
    if method == "analysis.signal":
        matches = [s for s in signals(db, p["trajectoryId"]) if s["id"] == p["id"]]
        if not matches:
            raise ValueError("Signal not found")
        signal = matches[0]
        manifest = signal["provenance"].get("inputManifestId")
        if manifest:
            signal["provenance"]["inputManifest"] = db.get("analysis_inputs", manifest)
        artifact = (
            db.maybe("artifacts", signal["artifactRef"]) if signal.get("artifactRef") else None
        )
        return {"signal": signal, "artifact": artifact}
    if method == "analysis.interpret":
        from tracelab.analysis.interpretation import interpret

        tid = p["trajectoryId"]
        return service.jobs.start(
            Job(kind="analysis", name="Interpret run outline", metadata={"trajectoryId": tid}),
            lambda job: interpret(service, job, tid, p["provider"], p["model"]),
        )
    if method == "analysis.overview":
        tid = p["trajectoryId"]
        events = await service.load_events(tid)

        def overview():
            semantic = semantic_events(events)
            segments = db.list("segments", "trajectory_id = ?", [tid])
            artifacts = db.list("artifacts", "trajectory_id = ?", [tid])
            interpretations = db.list("outline_nodes", "trajectory_id = ?", [tid])
            complete = [
                j
                for j in db.list("jobs", "data->>'status' = 'complete'", limit=100000)
                if j.get("metadata", {}).get("trajectoryId") == tid
                and j.get("name") == "Interpret run outline"
            ]
            trajectory = db.get("trajectories", tid)
            key = canonical_hash(
                {
                    "version": "overview-" + VERSION,
                    "events": events,
                    "segments": segments,
                    "artifacts": artifacts,
                    "interpretations": interpretations,
                    "jobs": [j["id"] for j in complete],
                    "capabilities": trajectory.get("capabilities"),
                }
            )
            cached = db.maybe("analysis_overviews", tid)
            if cached and cached["inputHash"] == key:
                return cached["overview"]
            outline = build_outline(tid, semantic, segments)
            if complete:
                latest = max(complete, key=lambda j: j["createdAt"])["id"]
                interpreted = [n for n in interpretations if n["provenance"].get("jobId") == latest]
                outline = [n for n in outline if n.kind in ("activity", "moment")] + [
                    OutlineNode.model_validate(n) for n in interpreted
                ]
            result = {
                "coordinates": coordinates(semantic),
                "eventCounts": counts(db, tid),
                "outline": [n.wire() for n in outline],
                "relationships": relationships(semantic),
                "analysisCapabilities": capabilities(
                    semantic, artifacts, db.get("trajectories", tid)
                ),
                "artifacts": artifacts,
            }

            db.put(
                "analysis_overviews",
                {"id": tid, "trajectoryId": tid, "inputHash": key, "overview": result},
            )
            return result

        return await asyncio.to_thread(overview)
    if method == "analysis.compare":
        return await compare(service, p["controlId"], p["treatmentId"])
    if method == "analysis.matchCandidates":
        control = db.get("trajectories", p["controlId"])
        field = p.get("field", "sampleId")

        def value(t):
            return (
                t.get("metadata", {}).get(field[9:])
                if field.startswith("metadata.")
                else t.get(field)
            )

        expected = value(control)
        experiment = db.get("experiments", control["experimentId"])
        candidates = db.list(
            "trajectories",
            "experiment_id IN (SELECT id FROM experiments WHERE workspace_id = ?)",
            [experiment["workspaceId"]],
            limit=10000,
        )
        return [
            t
            for t in candidates
            if expected is not None and value(t) == expected and t["id"] != control["id"]
        ]
    if method == "analysis.pairs":
        left = [db.get("trajectories", tid) for tid in p["controlIds"]]
        right = [db.get("trajectories", tid) for tid in p["treatmentIds"]]
        field = p.get("field", "sampleId")

        def key(t):
            return (
                t.get("metadata", {}).get(field[9:])
                if field.startswith("metadata.")
                else t.get(field)
            )

        pairs, ambiguous = [], []
        for t in left:
            matches = [r for r in right if key(t) is not None and key(r) == key(t)]
            if len(matches) == 1 and sum(key(c) == key(t) for c in left) == 1:
                pairs.append({"controlId": t["id"], "treatmentId": matches[0]["id"], "key": key(t)})
            elif matches:
                ambiguous.append(t["id"])
        return {"pairs": pairs, "ambiguous": ambiguous}
    if method == "analysis.artifact":
        item = ArtifactRef.model_validate(p)
        db.get("trajectories", item.trajectory_id)
        return db.put("artifacts", item)
    if method == "analysis.importParquet":
        from tracelab.analysis.artifacts import import_parquet

        events = await service.load_events(p["trajectoryId"])
        return await asyncio.to_thread(import_parquet, db, p["trajectoryId"], events, p)
    if method == "analysis.importSignals":
        source = ModelInternalSource.model_validate(p["source"])
        events = await service.load_events(source.trajectory_id)
        by_id = {e["id"]: e for e in events}
        for aid in source.artifact_ids:
            if db.get("artifacts", aid)["trajectoryId"] != source.trajectory_id:
                raise ValueError("Artifact belongs to another trajectory")
        items = [AnalysisSignal.model_validate(s) for s in p["signals"]]
        for item in items:
            if (
                item.trajectory_id != source.trajectory_id
                or item.artifact_ref not in source.artifact_ids
            ):
                raise ValueError("Signal must reference the declared trajectory and artifact")
            if (
                item.source_type not in ("probe", "sae", "logit", "custom")
                or item.channel != "WHITE_BOX"
            ):
                raise ValueError("Internal measurements require a white-box source type")
            if item.end_event_index >= len(events) or set(item.evidence_event_ids) - by_id.keys():
                raise ValueError("Signal references unavailable events")
            item.provenance = {**item.provenance, "internalSource": source.wire()}
        db.put("internal_sources", source)
        db.put_many("analysis_signals", items)
        return [i.wire() for i in items]
    raise ValueError("Unknown research command")
