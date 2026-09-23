from tracelab.ingestion.service import import_logs
from tracelab.models.domain import Job, Workspace, now


async def handle(service, method: str, p: dict):
    if method == "health":
        return {
            "version": "0.1.0",
            "inspectVersion": service.adapter.version,
            "dataDir": str(service.data_dir),
        }
    if method == "workspaces.list":
        return service.db.list("workspaces", order="data->>'openedAt' DESC")
    if method == "workspaces.create":
        return service.db.put("workspaces", Workspace(name=p.get("name", "Untitled workspace")))
    if method == "workspaces.open":
        w = service.db.get("workspaces", p["id"])
        w["openedAt"] = now()
        return service.db.put("workspaces", w)
    if method == "workspaces.demo":
        from tracelab.inspect_adapter.demo import create_demo

        return await create_demo(service)
    if method == "experiments.list":
        experiments = service.db.list("experiments", "workspace_id = ?", [p["workspaceId"]])
        counts = dict(
            service.db.query(
                "SELECT experiment_id, count(*) FROM trajectories GROUP BY experiment_id"
            )
        )
        return [e | {"trajectoryCount": counts.get(e["id"], 0)} for e in experiments]
    if method == "import":
        job = Job(
            kind="import", name="Import Inspect logs", metadata={"workspaceId": p["workspaceId"]}
        )
        return service.jobs.start(
            job, lambda j: import_logs(service, j, p["workspaceId"], p["path"])
        )
    raise ValueError("Unknown command")
