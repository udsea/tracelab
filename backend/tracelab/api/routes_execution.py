import asyncio
import os
import re
from urllib.parse import urlparse

from tracelab.comparison.service import compare_events, group_comparison
from tracelab.models.domain import (
    Experiment,
    Fork,
    Job,
    ProviderSettings,
)


async def handle(service, method: str, p: dict):
    if method == "forks.list":
        if p.get("trajectoryId"):
            return service.db.list("forks", "trajectory_id = ?", [p["trajectoryId"]])
        return service.db.list(
            "forks",
            "trajectory_id IN (SELECT id FROM trajectories WHERE experiment_id IN (SELECT id FROM experiments WHERE workspace_id = ?))",
            [p["workspaceId"]],
        )
    if method == "forks.run":
        fork = Fork.model_validate(p)
        if fork.fidelity != "context_only":
            raise ValueError("Checkpoint restoration is unavailable. Choose context-only.")
        service.db.put("forks", fork)
        for index, item in enumerate(fork.interventions):
            service.db.put(
                "interventions", {"id": f"{fork.id}:{index}", "parentId": fork.id, **item.wire()}
            )
        job = Job(
            kind="fork",
            name="Context-only fork",
            total=fork.replication_count,
            metadata={"forkId": fork.id},
        )

        async def execute(j):
            try:
                await service.forks.run(j, fork)
                from tracelab.analysis.branches import schedule_branch_analysis

                try:
                    analysis = schedule_branch_analysis(service, fork)
                    fork.metadata["analysisJobId"] = analysis["id"]
                    service.db.put("forks", fork)
                except Exception as analysis_error:
                    service.jobs.save(j, f"Branch analysis unavailable: {analysis_error}")
            except BaseException as exc:
                fork.status = "failed"
                fork.metadata["error"] = str(exc) or "Cancelled"
                service.db.put("forks", fork)
                raise

        return service.jobs.start(job, execute)
    if method == "compare.pair":
        (left, right) = (
            await service.load_events(p["left"]),
            await service.load_events(p["right"]),
        )
        right_t = service.db.get("trajectories", p["right"])
        fork = service.db.maybe("forks", right_t["forkId"]) if right_t.get("forkId") else None
        point = (
            fork["metadata"].get("sourceEventIndex")
            if fork and fork["sourceTrajectoryId"] == p["left"]
            else None
        )
        return {
            **(await asyncio.to_thread(compare_events, left, right, point)),
            "left": service.db.get("trajectories", p["left"]),
            "right": right_t,
        }
    if method == "compare.groups":
        return await asyncio.to_thread(group_comparison, service.db, p["workspaceId"], p["groups"])
    if method == "compare.members":
        from tracelab.comparison.service import group_members

        return await asyncio.to_thread(
            group_members, service.db, p["workspaceId"], p["group"], p["metric"], p.get("offset", 0)
        )
    if method == "jobs.list":
        return [
            {k: v for (k, v) in job.items() if k != "metadata"}
            | {
                "metadata": {
                    k: v
                    for (k, v) in job.get("metadata", {}).items()
                    if k not in ("provenance", "attempts", "definition", "schema")
                }
            }
            for job in await asyncio.to_thread(
                service.db.list, "jobs", limit=100, order="data->>'createdAt' DESC"
            )
        ]
    if method == "jobs.get":
        return await asyncio.to_thread(service.db.get, "jobs", p["id"])
    if method == "jobs.cancel":
        return service.jobs.cancel(p["id"])
    if method == "providers.list":
        return [
            cfg
            | {
                "configured": bool(os.environ.get(cfg["apiKeyEnv"]))
                or urlparse(cfg["baseUrl"]).hostname in ("localhost", "127.0.0.1", "::1")
            }
            for cfg in service.db.list("providers")
        ]
    if method == "providers.save":
        cfg = ProviderSettings.model_validate(p)
        url = urlparse(cfg.base_url)
        if (
            url.scheme not in ("http", "https")
            or not url.netloc
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Use an HTTP(S) endpoint without embedded credentials, query or fragment"
            )
        if not re.fullmatch("[A-Za-z_][A-Za-z0-9_]*", cfg.api_key_env):
            raise ValueError("Enter an environment variable name, not a credential")
        return service.db.put("providers", cfg)
    if method == "inspect.open":
        from tracelab.inspect_adapter.native import open_native

        experiment = Experiment.model_validate(service.db.get("experiments", p["experimentId"]))
        if experiment.source_type != "inspect" or (
            experiment.source_ref and experiment.source_ref.kind != "local"
        ):
            raise ValueError(
                "Native Inspect view currently opens local Inspect logs. Use the provenance panel to open remote sources."
            )
        return await open_native(service, experiment, p.get("sampleId"))
    raise ValueError("Unknown command")
