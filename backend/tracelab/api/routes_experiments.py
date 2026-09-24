"""Fork experiments use a distinct namespace; experiments.list still lists source logs."""

import asyncio

from tracelab.experiments.models import ForkExperimentSpec
from tracelab.experiments.preparation import preflight
from tracelab.experiments.queries import detail, listing

METHODS = {
    f"forkExperiments.{action}" for action in ("preview", "run", "resume", "list", "get", "trials")
}


async def handle(service, method, p):
    if method in ("forkExperiments.preview", "forkExperiments.run"):
        spec = ForkExperimentSpec.model_validate(
            {k: v for k, v in p.items() if k != "expectedSpecHash"}
        )
        if method.endswith(".preview"):
            return await preflight(service, spec)
        return await service.fork_experiments.start(spec, p.get("expectedSpecHash"))
    if method.endswith(".resume"):
        return await service.fork_experiments.resume(p["id"])
    offset, limit = int(p.get("offset", 0)), int(p.get("limit", 100))
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("Use nonnegative offset and limit 1–200")
    if method.endswith(".list"):
        return await asyncio.to_thread(listing, service, p["workspaceId"], offset, limit)
    if method.endswith(".get"):
        return await asyncio.to_thread(detail, service, p["id"], offset, limit)
    where, args = ["experiment_id=?"], [p["experimentId"]]
    for field in ("caseId", "armId", "status"):
        if p.get(field):
            where.append(f"(data->>'{field}') = ?")
            args.append(p[field])
    return await asyncio.to_thread(
        service.db.list,
        "fork_trials",
        " AND ".join(where),
        args,
        limit,
        offset,
        "CAST(data->>'scheduleOrdinal' AS INTEGER)",
    )
