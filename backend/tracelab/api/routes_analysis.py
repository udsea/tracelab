from tracelab.classifiers.runner import output_schema
from tracelab.ingestion.service import ensure_loaded
from tracelab.models.domain import Annotation, ClassifierDefinition, Job, Segment, now
from tracelab.segmentation.service import run_segmentation
from tracelab.storage.queries import list_trajectories


async def handle(service, method: str, p: dict):
    if method == "annotations.save":
        item = Annotation.model_validate(p)
        trajectory = await ensure_loaded(service, item.trajectory_id)
        if item.end_event_index >= trajectory.event_count:
            raise ValueError("Annotation extends beyond this trajectory")
        return service.db.put("annotations", item)
    if method == "annotations.delete":
        service.db.delete("annotations", p["id"])
        return True
    if method == "segments.save":
        item = Segment.model_validate(p)
        trajectory = await ensure_loaded(service, item.trajectory_id)
        if item.end_event >= trajectory.event_count:
            raise ValueError("Segment extends beyond this trajectory")
        if item.parent_id:
            parent = service.db.get("segments", item.parent_id)
            if parent["trajectoryId"] != item.trajectory_id or parent.get("parentId"):
                raise ValueError("Only one episode level is supported")
            if not parent["startEvent"] <= item.start_event <= item.end_event <= parent["endEvent"]:
                raise ValueError("Episode must remain within its phase")
        item.provenance = {**item.provenance, "manualEditAt": now()}
        return service.db.put("segments", item)
    if method == "segments.delete":
        service.db.query("DELETE FROM segments WHERE id = ? OR parent_id = ?", [p["id"], p["id"]])
        return True
    if method == "segments.run":
        job = Job(
            kind="segmentation",
            name="Segment trajectory",
            metadata={"trajectoryId": p["trajectoryId"]},
        )
        return service.jobs.start(
            job,
            lambda j: run_segmentation(
                service, j, p["trajectoryId"], p["provider"], p["model"], p.get("rerun", False)
            ),
        )
    if method == "classifiers.list":
        return service.db.list(
            "classifier_definitions",
            "workspace_id IS NULL OR workspace_id = ?",
            [p.get("workspaceId")],
        )
    if method == "classifiers.save":
        item = ClassifierDefinition.model_validate(p)
        if item.workspace_id:
            service.db.get("workspaces", item.workspace_id)
        output_schema(item)
        return service.db.put("classifier_definitions", item)
    if method == "classifiers.run":
        definition = ClassifierDefinition.model_validate(
            service.db.get("classifier_definitions", p["classifierId"])
        )
        ids = p.get("trajectoryIds")
        if ids is None:
            ids = [
                t["id"]
                for t in list_trajectories(
                    service.db,
                    p.get("workspaceId"),
                    p.get("experimentId"),
                    p.get("filters"),
                    limit=500,
                )["items"]
            ]
            from tracelab.storage.queries import trajectory_filter

            (where, args) = trajectory_filter(
                p.get("workspaceId"), p.get("experimentId"), p.get("filters")
            )
            ids = [
                r[0] for r in service.db.query(f"SELECT id FROM trajectories WHERE {where}", args)
            ]
        if not ids:
            raise ValueError("Select at least one trajectory")
        job = Job(
            kind="classifier",
            name=definition.name,
            concurrency=max(1, min(int(p.get("concurrency", 4)), 16)),
            metadata={"trajectoryIds": ids, "classifierId": definition.id},
        )
        return service.jobs.start(
            job,
            lambda j: service.classifiers.run(
                j, definition, ids, p.get("eventIds"), p.get("rerun", False)
            ),
        )
    if method == "results.get":
        return service.db.get("classifier_results", p["id"])
    raise ValueError("Unknown command")
