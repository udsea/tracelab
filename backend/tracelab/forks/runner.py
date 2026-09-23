import asyncio
import copy
import subprocess

from tracelab import __version__
from tracelab.classifiers.runner import canonical_hash
from tracelab.forks.context import apply_interventions, context_messages
from tracelab.inspect_adapter.normalize import normalize_sample
from tracelab.models.domain import Fork, Job, ProviderSettings, Trajectory, now, uid


class ForkRunner:
    def __init__(self, db, jobs, adapter, load_events, data_dir):
        self.db, self.jobs, self.adapter = db, jobs, adapter
        self.load_events, self.data_dir = load_events, data_dir
        self.execution_lock = asyncio.Lock()  # Inspect owns process-level eval context.

    async def run(self, job: Job, fork: Fork):
        if fork.fidelity != "context_only":
            raise ValueError("Checkpoint restoration is unavailable for this adapter")
        parent = Trajectory.model_validate(self.db.get("trajectories", fork.source_trajectory_id))
        all_events = await self.load_events(parent.id)
        if parent.capabilities and not parent.capabilities.context_fork:
            raise ValueError(parent.capabilities.reason)
        source = next((e for e in all_events if e["id"] == fork.source_event_id), None)
        if not source:
            raise ValueError("Source event does not belong to source trajectory")
        prefix = [e for e in all_events if e["index"] <= source["index"]]
        edited, appended, config = apply_interventions(prefix, fork)
        messages = context_messages(edited, appended)
        model = config.get("model") or parent.model
        provider_id = config.get("provider", "openai")
        if not model:
            raise ValueError("A continuation model is required")
        provider = ProviderSettings.model_validate(self.db.get("providers", provider_id))
        try:
            commit = (
                subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2
                ).stdout.strip()
                or None
            )
        except (OSError, subprocess.TimeoutExpired):
            commit = None
        fork.metadata |= {
            "sourceExperiment": parent.experiment_id,
            "sourceEventIndex": source["index"],
            "inspectVersion": self.adapter.version,
            "traceLabVersion": __version__,
            "gitCommit": commit,
            "model": model,
            "provider": provider.wire(),
            "parameters": config.get("parameters", {}),
            "inputHash": canonical_hash(messages),
            "context": messages,
            "executionMode": "single_model_continuation",
            "contextReconstruction": "normalized_recorded_prefix",
            "toolsRestored": False,
            "jobId": job.id,
        }
        fork.status = "running"
        self.db.put("forks", fork)
        job.total = fork.replication_count
        current = None
        failures = []
        try:
            for replication in range(fork.replication_count):
                current = Trajectory(
                    id=uid("traj"),
                    experiment_id=parent.experiment_id,
                    sample_id=f"{parent.sample_id} / branch {replication + 1}",
                    model=model,
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
                        "executionMode": "single_model_continuation",
                        "jobId": job.id,
                    },
                )
                fork.child_trajectory_ids.append(current.id)
                self.db.put("forks", fork)
                self.db.put("trajectories", current)
                copied = []
                for index, event in enumerate(edited):
                    cloned = copy.deepcopy(event)
                    cloned.update(
                        id=f"{current.id}:e{index}",
                        trajectoryId=current.id,
                        index=index,
                        parentEventIds=[f"{current.id}:e{index - 1}"] if index else [],
                    )
                    cloned["metadata"]["sourceEventId"] = event["id"]
                    copied.append(cloned)
                for msg in appended:
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
                parameters = dict(config.get("parameters", {}))
                if isinstance(parameters.get("seed"), int):
                    parameters["seed"] += replication
                current.metadata["parameters"] = parameters
                self.jobs.save(
                    job,
                    f"Replication {replication + 1}/{fork.replication_count}: model continuation started",
                )
                try:
                    async with self.execution_lock:
                        result = await self.adapter.run_fork(
                            {
                                "messages": messages,
                                "model": model,
                                "provider": provider.wire(),
                                "parameters": parameters,
                                "log_dir": str(
                                    self.data_dir / "fork-logs" / fork.id / str(replication + 1)
                                ),
                                "sample_id": current.id,
                                "metadata": {"tracelabForkId": fork.id, "fidelity": fork.fidelity},
                            }
                        )
                    sample = result["sample"]
                    # Only generated output follows the edited prefix. The log keeps the entire replay input.
                    output = sample.get("output") or {}
                    choices = output.get("choices") or []
                    generated, sources = normalize_sample(
                        current.id + ":continuation",
                        {"messages": [choices[0]["message"]] if choices else [], "output": output},
                    )
                    offset = len(copied)
                    for i, event in enumerate(generated):
                        event.id = f"{current.id}:e{offset + i}"
                        event.index = offset + i
                        event.trajectory_id = current.id
                        event.parent_event_ids = (
                            [f"{current.id}:e{offset + i - 1}"] if offset + i else []
                        )
                    self.db.put_many("events", generated)
                    self.db.put_many("source_records", sources)
                    current.event_count += len(generated)
                    current.status = "unknown"  # No inherited or invented outcome/score.
                    usage = output.get("usage") or {}
                    current.input_tokens = usage.get("input_tokens")
                    current.output_tokens = usage.get("output_tokens")
                    current.total_tokens = usage.get("total_tokens")
                    current.metadata |= {
                        "executionStatus": "complete",
                        "logPath": result["logPath"],
                        "outcomeNote": "Model continuation completed; task outcome not scored.",
                    }
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    current.status = "error"
                    current.metadata["executionError"] = str(exc)
                    failures.append(str(exc))
                    self.jobs.save(job, f"Replication {replication + 1} failed: {exc}")
                current.completed_at = now()
                from datetime import datetime

                current.duration_ms = (
                    datetime.fromisoformat(current.completed_at)
                    - datetime.fromisoformat(current.started_at)
                ).total_seconds() * 1000
                self.db.put("trajectories", current)
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
            if current and current.status == "running":
                current.status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "error"
                self.db.put("trajectories", current)
            raise
        finally:
            self.db.put("forks", fork)
