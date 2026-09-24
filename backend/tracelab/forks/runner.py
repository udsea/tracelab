import asyncio
import copy
import subprocess
from datetime import datetime

from tracelab import __version__
from tracelab.forks.execution import MODE, NOTE, ReplayExecution
from tracelab.forks.preparation import PreparedFork, prepare
from tracelab.forks.replay import POLICY, ReplayUnsupported
from tracelab.inspect_adapter.normalize import normalize_sample
from tracelab.models.domain import Fork, Job, Trajectory, now, uid


class ForkRunner:
    def __init__(self, db, jobs, adapter, load_events, data_dir):
        self.db, self.jobs, self.adapter = db, jobs, adapter
        self.load_events, self.data_dir = load_events, data_dir
        self.execution_lock = asyncio.Lock()

    async def prepare(self, fork: Fork) -> PreparedFork:
        return await prepare(self, fork)

    async def run(self, job: Job, fork: Fork, prepared: PreparedFork | None = None):
        prepared = prepared or await self.prepare(fork)
        multi = prepared.execution_spec.continuation == "multi_step"
        if multi and not prepared.replay_support["supported"]:
            fork.metadata["replaySupport"] = prepared.replay_support
            self.db.put("forks", fork)
            raise ReplayUnsupported(
                prepared.replay_support["reasonCode"], prepared.replay_support["reason"]
            )
        try:
            commit = (
                subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2
                ).stdout.strip()
                or None
            )
        except (OSError, subprocess.TimeoutExpired):
            commit = None
        fork.metadata.update(
            sourceExperiment=prepared.parent.experiment_id,
            sourceEventIndex=prepared.source_event["index"],
            inspectVersion=self.adapter.version,
            traceLabVersion=__version__,
            gitCommit=commit,
            model=prepared.model,
            provider=prepared.provider.wire(),
            parameters=prepared.generation_parameters,
            inputHash=prepared.input_hash,
            context=prepared.messages,
            executionHash=prepared.execution_hash,
            executionMode=MODE if multi else "single_model_continuation",
            executionSpec=prepared.execution_spec.wire(),
            replayPlanHash=prepared.replay_plan_hash,
            toolCatalog=prepared.tool_catalog.wire() if prepared.tool_catalog else None,
            replayPlan=prepared.preview()["replayPlan"],
            contextReconstruction="normalized_recorded_prefix",
            toolsRestored=False,
            jobId=job.id,
        )
        fork.status = "running"
        self.db.put("forks", fork)
        job.total = fork.replication_count
        failures = []
        try:
            for replication in range(fork.replication_count):
                child = await self.run_replication(prepared, replication, job)
                if child.status == "error":
                    failures.append(child.metadata.get("executionError", "Branch execution failed"))
                job.completed += 1
                self.jobs.save(job)
            if failures:
                raise RuntimeError(f"{len(failures)} replications failed. {failures[0]}")
            fork.status = "complete"
        except BaseException as exc:
            fork.status = "failed"
            fork.metadata["error"] = (
                "Cancelled" if isinstance(exc, asyncio.CancelledError) else str(exc)
            )
            raise
        finally:
            self.db.put("forks", fork)

    async def run_replication(self, prepared: PreparedFork, replication: int, job: Job):
        fork, parent = prepared.fork, prepared.parent
        multi = prepared.execution_spec.continuation == "multi_step"
        parameters = dict(prepared.generation_parameters)
        if isinstance(parameters.get("seed"), int):
            parameters["seed"] += replication
        current = Trajectory(
            id=uid("traj"),
            experiment_id=parent.experiment_id,
            sample_id=f"{parent.sample_id} / branch {replication + 1}",
            model=prepared.model,
            task=parent.task,
            condition="intervention",
            status="running",
            loaded=True,
            parent_trajectory_id=parent.id,
            fork_id=fork.id,
            started_at=now(),
            metadata={
                "fidelity": "context_only",
                "replication": replication + 1,
                "jobId": job.id,
                "executionMode": MODE if multi else "single_model_continuation",
                "parameters": parameters,
                "executionHash": prepared.execution_identity(parameters),
                "inputHash": prepared.input_hash,
                "executionSpec": prepared.execution_spec.wire(),
                "environment": "none",
                "environmentRestored": False,
                "toolExecution": False,
                "toolsRestored": False,
                "scoring": "none",
            },
        )
        if multi:
            current.metadata.update(
                toolPolicy="recorded_replay",
                replayMatchPolicy=POLICY,
                toolCatalogHash=prepared.tool_catalog.canonical_hash,
                replayPlanHash=prepared.replay_plan_hash,
                provenanceNote=NOTE,
            )
        fork.child_trajectory_ids.append(current.id)
        self.db.put("forks", fork)
        self.db.put("trajectories", current)
        execution = ReplayExecution(self.db, current, prepared) if multi else None
        try:
            copied = []
            for index, event in enumerate(prepared.edited_events):
                cloned = copy.deepcopy(event)
                cloned.update(
                    id=f"{current.id}:e{index}",
                    trajectoryId=current.id,
                    index=index,
                    parentEventIds=[f"{current.id}:e{index - 1}"] if index else [],
                )
                cloned["metadata"]["sourceEventId"] = event["id"]
                copied.append(cloned)
            for msg in prepared.appended_messages:
                index = len(copied)
                copied.append(
                    {
                        "id": f"{current.id}:e{index}",
                        "trajectoryId": current.id,
                        "index": index,
                        "type": msg["role"],
                        "role": msg["role"],
                        "content": msg["content"],
                        "parentEventIds": [copied[-1]["id"]] if copied else [],
                        "metadata": {"intervened": True},
                    }
                )
            self.db.put_many("events", copied)
            current.event_count = len(copied)
            self.db.put("trajectories", current)
            self.jobs.save(
                job, f"Replication {replication + 1}/{fork.replication_count}: continuation started"
            )
            request = {
                "messages": copy.deepcopy(prepared.messages),
                "model": prepared.model,
                "provider": prepared.provider.wire(),
                "parameters": parameters,
                "log_dir": str(self.data_dir / "fork-logs" / fork.id / str(replication + 1)),
                "sample_id": current.id,
                "metadata": {
                    "tracelabForkId": fork.id,
                    "fidelity": fork.fidelity,
                    "executionHash": current.metadata["executionHash"],
                    "executionMode": current.metadata["executionMode"],
                },
            }
            current.metadata["logDirectory"] = request["log_dir"]
            self.db.put("trajectories", current)
            if multi:
                request.update(execution=execution, tool_catalog=prepared.tool_catalog)
            async with self.execution_lock:
                result = await self.adapter.run_fork(request)
            current.metadata["logPath"] = result["logPath"]
            if multi:
                execution.finish()
            else:
                self.save_single_output(current, result)
        except asyncio.CancelledError:
            if execution:
                execution.finish("cancelled")
            else:
                current.status = "cancelled"
                current.metadata.update(executionStatus="cancelled", terminationReason="cancelled")
            raise
        except Exception as exc:
            current.status = "error"
            current.metadata.update(
                executionError=str(exc), executionStatus="error", terminationReason="model_error"
            )
            if execution:
                execution.finish(
                    "tool_resolution_error"
                    if execution.termination == "tool_resolution_error"
                    else "model_error"
                )
            self.jobs.save(job, f"Replication {replication + 1} failed: {exc}")
        finally:
            current.completed_at = now()
            current.duration_ms = (
                datetime.fromisoformat(current.completed_at)
                - datetime.fromisoformat(current.started_at)
            ).total_seconds() * 1000
            self.db.put("trajectories", current)
        return current

    def save_single_output(self, current, result):
        output = result["sample"].get("output") or {}
        choices = output.get("choices") or []
        generated, sources = normalize_sample(
            current.id + ":continuation",
            {"messages": [choices[0]["message"]] if choices else [], "output": output},
        )
        offset = current.event_count
        for i, event in enumerate(generated):
            event.id, event.index, event.trajectory_id = (
                f"{current.id}:e{offset + i}",
                offset + i,
                current.id,
            )
            event.parent_event_ids = [f"{current.id}:e{offset + i - 1}"] if offset + i else []
        self.db.put_many("source_records", sources)
        self.db.put_many("events", generated)
        current.event_count += len(generated)
        current.status = "unknown"
        usage = output.get("usage") or {}
        current.input_tokens, current.output_tokens, current.total_tokens = (
            usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")
        )
        current.metadata.update(
            executionStatus="complete",
            terminationReason="assistant_completed",
            outcomeNote="Model continuation completed; task outcome not scored.",
        )
