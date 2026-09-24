from collections import Counter

from tracelab.analysis.models import AnalysisSignal
from tracelab.analysis.projection import signals
from tracelab.classifiers.runner import canonical_hash
from tracelab.comparison.service import compare_events
from tracelab.models.domain import now


def distribution(events, field):
    values = Counter(
        (e.get("tool") or {}).get("name") if field == "tools" else e["type"] for e in events
    )
    values.pop(None, None)
    return dict(values)


def delta(left, right):
    return {
        k: {
            "control": left.get(k, 0),
            "treatment": right.get(k, 0),
            "delta": right.get(k, 0) - left.get(k, 0),
        }
        for k in sorted(left.keys() | right.keys())
    }


def signal_summary(rows):
    groups = {}
    for row in rows:
        # Never combine different detector definitions under an equal display name.
        key = row.get("metadata", {}).get("laneId") or row["name"]
        if row.get("score") is not None and row["sourceType"] != "rule":
            groups.setdefault(key, []).append(row["score"])
    return {key: sum(values) / len(values) for key, values in groups.items()}


def completed_rules(db, tid):
    definitions = {}
    for job in db.list("jobs", "(data->>'kind') = 'analysis'", limit=100000):
        meta = job.get("metadata", {})
        records = list(meta.get("completedDetectors", []))
        if (
            job["status"] == "complete"
            and meta.get("definition")
            and tid in meta.get("trajectoryIds", [])
        ):
            records.append({"trajectoryId": tid, "definition": meta["definition"]})
        for record in records:
            definition = record["definition"]
            if record["trajectoryId"] == tid and definition["detectorType"] == "rule":
                definitions[definition["id"]] = definition
    return definitions


def rule_counts(db, tid, rows):
    counts = {key: 0 for key in completed_rules(db, tid)}
    for row in rows:
        key = row.get("provenance", {}).get("detectorId")
        if row["sourceType"] == "rule" and key and row.get("metadata", {}).get("matchCount") != 0:
            counts[key] = counts.get(key, 0) + 1
    return counts


async def compare(service, control_id, treatment_id):
    left, right = await service.load_events(control_id), await service.load_events(treatment_id)
    control, treatment = (
        service.db.get("trajectories", control_id),
        service.db.get("trajectories", treatment_id),
    )
    left_signals, right_signals = signals(service.db, control_id), signals(service.db, treatment_id)
    ls, rs = signal_summary(left_signals), signal_summary(right_signals)
    lc, rc = (
        rule_counts(service.db, control_id, left_signals),
        rule_counts(service.db, treatment_id, right_signals),
    )
    rule_shared = lc.keys() & rc.keys()
    shared = ls.keys() & rs.keys()
    fork = service.db.maybe("forks", treatment.get("forkId")) if treatment.get("forkId") else None
    intervention = (fork or {}).get("metadata", {}).get("sourceEventIndex")
    alignment = compare_events(left, right, intervention)
    return {
        "control": control,
        "treatment": treatment,
        "alignment": alignment,
        "tools": delta(distribution(left, "tools"), distribution(right, "tools")),
        "eventTypes": delta(distribution(left, "events"), distribution(right, "events")),
        "signals": {
            k: {"control": ls[k], "treatment": rs[k], "delta": rs[k] - ls[k]} for k in shared
        },
        "ruleMatchCounts": {
            k: {"control": lc[k], "treatment": rc[k], "delta": rc[k] - lc[k]} for k in rule_shared
        },
        "unmatchedSignals": sorted((ls.keys() ^ rs.keys()) | (lc.keys() ^ rc.keys())),
        "metrics": {
            k: {
                "control": control.get(k),
                "treatment": treatment.get(k),
                "delta": treatment[k] - control[k]
                if isinstance(control.get(k), (int, float))
                and isinstance(treatment.get(k), (int, float))
                else None,
            }
            for k in ("status", "scores", "durationMs", "totalTokens", "eventCount")
        },
        "interpretation": "Observed branch comparison; descriptive differences are not causal proof. Missing signals are not zero.",
        "provenance": {
            "inputTrajectoryIds": [control_id, treatment_id],
            "inputHashes": [canonical_hash(left), canonical_hash(right)],
            "createdAt": now(),
            "implementationVersion": "contrastive-v1",
        },
    }


class ContrastiveDetector:
    detector_type = "contrastive"

    def __init__(self, service):
        self.service = service

    async def run(self, trajectory_ids, config):
        if len(trajectory_ids) != 2:
            raise ValueError("Contrastive analysis requires a control and treatment pair")
        result = await compare(self.service, *trajectory_ids)
        point = result["alignment"]["firstBehaviouralDivergence"]
        if not point or point.get("right") is None:
            return []
        events = await self.service.load_events(trajectory_ids[1])
        index = point["right"]
        return [
            AnalysisSignal(
                trajectory_id=trajectory_ids[1],
                name="Observed behavioral divergence",
                source_type="contrastive",
                start_event_index=index,
                end_event_index=index,
                label="first_divergence",
                evidence_event_ids=[e["id"] for e in events if e["index"] == index],
                provenance={
                    **result["provenance"],
                    "definition": config,
                    "detectorId": config.get("id"),
                    "version": config.get("version"),
                    "parameters": config.get("parameters", {}),
                    "rawResult": result,
                },
                metadata={
                    "laneId": str(config.get("id", "contrastive")) + ":first_divergence",
                    "comparison": result,
                },
            )
        ]
