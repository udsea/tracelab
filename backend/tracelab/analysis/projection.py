"""Existing records project into the common signal model without storage migration."""

import json

from tracelab.analysis.models import AnalysisSignal
from tracelab.analysis.semantic import timestamp_ms


def signals(db, tid):
    results = db.query(
        "SELECT data FROM current_classifier_results WHERE trajectory_id = ? ORDER BY event_index",
        [tid],
    )
    output = []
    for row in results:
        r = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        value = r.get("output") or {}
        definition = (
            r.get("provenance", {}).get("definition")
            or db.maybe("classifier_definitions", r["classifierId"])
            or {}
        )
        output.append(
            AnalysisSignal(
                id="llm:" + r["id"],
                trajectory_id=tid,
                name=definition.get("name", r["classifierId"]),
                source_type="llm",
                start_event_index=r["startEventIndex"],
                end_event_index=r["endEventIndex"],
                score=value.get("score"),
                label=value.get("label"),
                evidence_event_ids=value.get("evidenceEventIds", []),
                provenance={
                    **r.get("provenance", {}),
                    "createdAt": r.get("createdAt"),
                    "resultId": r["id"],
                    "detectorId": r["classifierId"],
                    "inputTrajectoryIds": [tid],
                    "implementationVersion": "classifier-projection-v1",
                    "rawResult": value,
                },
                metadata={"output": value, "error": r.get("error"), "laneId": r["classifierId"]},
            ).wire()
        )
    for a in db.list("annotations", "trajectory_id = ?", [tid]):
        output.append(
            AnalysisSignal(
                id="human:" + a["id"],
                trajectory_id=tid,
                name=a["label"],
                source_type="human",
                start_event_index=a["startEventIndex"],
                end_event_index=a["endEventIndex"],
                label=a["label"],
                provenance={"annotationId": a["id"], "createdAt": a["createdAt"], "rawResult": a},
                metadata={"note": a.get("note"), "laneId": "human"},
            ).wire()
        )
    # Keep historical records but show only the most recent completed detector run.
    latest = {}
    for job in db.list(
        "jobs", "(data->>'kind') = 'analysis' AND (data->>'status') = 'complete'", limit=100000
    ):
        meta = job.get("metadata", {})
        records = list(meta.get("completedDetectors", []))
        if tid in meta.get("trajectoryIds", []) and meta.get("definition"):
            records.append({"trajectoryId": tid, "definition": meta["definition"]})
        for record in records:
            key = record["definition"]["id"]
            if record["trajectoryId"] == tid and (
                key not in latest or job["createdAt"] > latest[key][0]
            ):
                latest[key] = (job["createdAt"], job["id"])
    for signal in db.list(
        "analysis_signals", "trajectory_id = ?", [tid], limit=100000, order="event_index"
    ):
        provenance = signal.get("provenance", {})
        detector = provenance.get("detectorId")
        if detector not in latest or provenance.get("jobId") == latest[detector][1]:
            output.append(signal)
    for fork in db.list("forks", "trajectory_id = ?", [tid]):
        index = fork.get("metadata", {}).get("sourceEventIndex")
        if index is not None:
            output.append(
                AnalysisSignal(
                    id="fork:" + fork["id"],
                    trajectory_id=tid,
                    name="Forks",
                    source_type="intervention",
                    start_event_index=index,
                    end_event_index=index,
                    label=fork["status"],
                    evidence_event_ids=[fork["sourceEventId"]],
                    provenance={"forkId": fork["id"], "rawResult": fork},
                    metadata={"laneId": "forks"},
                ).wire()
            )
    for event in db.list(
        "events",
        "trajectory_id = ? AND ((data->>'type') = 'environment' OR (data->'metadata'->>'environmentEffects') IS NOT NULL)",
        [tid],
        limit=100000,
        order="event_index",
    ):
        meta = event.get("metadata", {})
        if meta.get("structuralKind") in ("agent", "span", "scope") and not meta.get(
            "environmentEffects"
        ):
            continue
        output.append(
            AnalysisSignal(
                id="environment:" + event["id"],
                trajectory_id=tid,
                name="Environment observations",
                source_type="environment",
                channel="GRAY_BOX",
                start_event_index=event["index"],
                end_event_index=event["index"],
                label=meta.get("environmentType", "recorded_environment_state"),
                evidence_event_ids=[event["id"]],
                provenance={
                    "inputEventIds": [event["id"]],
                    "sourceRecordId": meta.get("sourceRecordId"),
                    "implementationVersion": "environment-projection-v1",
                },
                metadata={
                    "laneId": "environment-observations",
                    "summary": (event.get("content") or "")[:600],
                },
            ).wire()
        )
    return output


def capabilities(events, artifacts, trajectory):
    measurements = {a.get("metadata", {}).get("measurement") for a in artifacts}
    return {
        "transcript": any(e.type in ("assistant", "user", "reasoning") for e in events),
        "tools": any(e.tool_name for e in events),
        "environment": any(e.environment_effects or e.type == "environment" for e in events),
        "timing": any(
            timestamp_ms(e.timestamp) is not None or e.duration_ms is not None for e in events
        ),
        "logits": "logit" in measurements,
        "activations": "activation" in measurements,
        "probes": "probe" in measurements,
        "saeFeatures": "sae" in measurements,
        "contextFork": (trajectory.get("capabilities") or {}).get("contextFork", False),
        "checkpointFork": (trajectory.get("capabilities") or {}).get("checkpointFork", False),
    }


def signal_summaries(db, tid):
    """Keep exact prompts, raw responses and large input lists behind the detail API."""
    rows = signals(db, tid)
    for row in rows:
        row["provenance"] = {
            key: row["provenance"][key]
            for key in ("detectorId", "createdAt", "implementationVersion", "inputHash")
            if key in row["provenance"]
        }
        row["metadata"] = {
            key: row["metadata"][key]
            for key in ("laneId", "error", "peakEventIndex")
            if key in row["metadata"]
        }
        row["metadata"]["evidenceCount"] = len(row["evidenceEventIds"])
        row["evidenceEventIds"] = []
    return rows
