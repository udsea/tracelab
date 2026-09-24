import asyncio

from tracelab.ingestion.service import ensure_loaded
from tracelab.models.domain import (
    Job,
)
from tracelab.presentation.storage import counts, ensure_presentations
from tracelab.storage.queries import (
    event_location,
    event_page,
    list_trajectories,
    result_summaries,
    search,
)


async def handle(service, method: str, p: dict):
    if method == "trajectories.get":
        trajectory = await ensure_loaded(service, p["id"])
        return await asyncio.to_thread(trajectory_detail, service, trajectory)
    if method in ("events.list", "events.locate", "timeline"):
        await ensure_loaded(service, p["trajectoryId"])
        return await asyncio.to_thread(read, service, method, p)
    if method == "events.get":
        if "id" not in p:
            await ensure_loaded(service, p["trajectoryId"])
            rows = await asyncio.to_thread(
                service.db.list,
                "events",
                "trajectory_id = ? AND event_index = ?",
                [p["trajectoryId"], int(p["index"])],
                limit=1,
            )
            if not rows:
                raise ValueError("This event is not indexed yet")
            p = {"id": rows[0]["id"]}
        if not service.db.maybe("events", p["id"]):
            await ensure_loaded(service, p["id"].rsplit(":e", 1)[0])
        return await asyncio.to_thread(read, service, method, p)
    if method == "search.index":
        from tracelab.storage.queries import trajectory_filter

        (where, args) = trajectory_filter(p["workspaceId"])
        rows = await asyncio.to_thread(
            service.db.query, f"SELECT id FROM trajectories WHERE {where}", args
        )
        ids = [r[0] for r in rows]

        async def index(j):
            for tid in ids:
                await ensure_loaded(service, tid)
                j.completed += 1
                service.jobs.save(j)
                await asyncio.sleep(0)

        return service.jobs.start(
            Job(kind="index", name="Index event content", total=len(ids)), index
        )
    return await asyncio.to_thread(read, service, method, p)


def trajectory_detail(service, trajectory):
    return {
        "trajectory": trajectory.wire(),
        "eventCounts": counts(service.db, trajectory.id),
        "capabilities": (
            {
                **trajectory.capabilities.wire(),
                "contextOnly": trajectory.capabilities.context_fork,
                "checkpointRestored": trajectory.capabilities.checkpoint_fork,
            }
            if trajectory.capabilities
            else service.adapter.list_checkpoints(trajectory)
        ),
    }


def read(service, method, p):
    if method == "trajectories.summary":
        return service.db.get("trajectories", p["id"])
    if method == "trajectories.list":
        return list_trajectories(
            service.db,
            p.get("workspaceId"),
            p.get("experimentId"),
            p.get("filters"),
            p.get("offset", 0),
            p.get("limit", 100),
        )
    if method == "events.list":
        return event_page(
            service.db,
            p["trajectoryId"],
            p.get("offset", 0),
            p.get("limit", 100),
            p.get("mode", "all"),
            p.get("query", ""),
            p.get("start"),
            p.get("end"),
        )
    if method == "events.locate":
        return event_location(
            service.db,
            p["trajectoryId"],
            int(p["eventIndex"]),
            p.get("mode", "all"),
            p.get("query", ""),
            p.get("start"),
            p.get("end"),
        )
    if method == "events.get":
        event = service.db.get("events", p["id"])
        ensure_presentations(service.db, event["trajectoryId"])
        event = service.db.get("event_presentations", event["id"])
        results = result_summaries(service.db, event["trajectoryId"], event["index"])
        return {"event": event, "results": results}
    if method == "events.raw":
        event = service.db.get("events", p["id"])
        rid = event["metadata"].get("sourceRecordId")
        return service.db.get("source_records", rid) if rid else event["metadata"].get("raw", event)
    if method == "timeline":
        tid = p["trajectoryId"]
        markers = service.db.query(
            "SELECT id, event_index, data->>'type', data->'tool'->>'name',\n                data->'tool'->>'error', data->>'tokenUsage', data->'metadata'->>'agentId' FROM events WHERE trajectory_id = ? ORDER BY event_index",
            [tid],
        )
        results = result_summaries(service.db, tid)
        return {
            "markers": [
                {
                    "id": r[0],
                    "index": r[1],
                    "type": r[2],
                    "tool": r[3],
                    "error": bool(r[4]),
                    "usage": r[5],
                    "agent": r[6],
                }
                for r in markers
            ],
            "segments": service.db.list(
                "segments",
                "trajectory_id = ?",
                [tid],
                order="TRY_CAST(data->>'startEvent' AS INTEGER)",
            ),
            "annotations": service.db.list("annotations", "trajectory_id = ?", [tid]),
            "checkpoints": service.db.list("checkpoints", "trajectory_id = ?", [tid]),
            "forks": service.db.list("forks", "trajectory_id = ?", [tid]),
            "results": results,
        }
    if method == "search":
        return search(service.db, p["workspaceId"], p["query"])
    raise ValueError("Unknown command")
