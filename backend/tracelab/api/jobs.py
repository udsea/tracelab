import asyncio
from collections.abc import Awaitable, Callable

from tracelab.models.domain import Job, now
from tracelab.storage.database import Database


class Jobs:
    def __init__(self, db: Database):
        self.db = db
        self.tasks: dict[str, asyncio.Task] = {}
        self.active: dict[str, Job] = {}
        for old in db.list("jobs", "(data->>'status') IN ('queued','running')"):
            old.update(
                status="failed",
                error="Backend stopped before completion. Partial artifacts are retained.",
                completedAt=now(),
            )
            db.put("jobs", old)
            if old["kind"] == "classifier":
                db.put("classifier_runs", old)
        for old in db.list("forks", "(data->>'status') = 'running'"):
            old.update(status="failed")
            old["metadata"]["error"] = "Backend stopped before completion"
            db.put("forks", old)
        for old in db.list(
            "trajectories", "(data->>'status') = 'running' AND (data->>'forkId') IS NOT NULL"
        ):
            old.update(status="error")
            old["metadata"]["executionError"] = "Backend stopped before completion"
            db.put("trajectories", old)
        for old in db.list(
            "trajectories",
            "(data->'metadata'->>'indexState') IN ('INDEXING','PARTIALLY_AVAILABLE') OR "
            "((data->'metadata'->>'indexState') = 'METADATA_READY' AND "
            "(data->'metadata'->>'importFormat') != 'inspect' AND "
            "(data->'metadata'->>'indexJobId') IS NOT NULL)",
        ):
            old["metadata"].update(
                indexState="ERROR",
                indexError="Indexing interrupted by backend shutdown. Available events are preserved; retry to finish.",
            )
            db.put("trajectories", old)

    def save(self, job: Job, message: str | None = None):
        if message:
            job.logs = (job.logs + [f"{now()}  {message}"])[-200:]
        self.db.put("jobs", job)
        if job.kind == "classifier":
            self.db.put("classifier_runs", job)

    def start(self, job: Job, run: Callable[[Job], Awaitable[None]]) -> dict:
        self.save(job)
        self.active[job.id] = job

        async def wrapper():
            try:
                job.status = "running"
                self.save(job, "Started")
                await run(job)
                job.status = "complete"
            except asyncio.CancelledError:
                job.status = "cancelled"
                self.save(job, "Cancelled; completed results remain available")
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
                self.save(job, f"Failed: {exc}")
            finally:
                job.completed_at = now()
                self.save(job)
                self.tasks.pop(job.id, None)
                self.active.pop(job.id, None)

        self.tasks[job.id] = asyncio.create_task(wrapper())
        return job.wire()

    def cancel(self, id: str):
        if id in self.tasks:
            self.tasks[id].cancel()
        return {"id": id, "requested": id in self.tasks}

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
