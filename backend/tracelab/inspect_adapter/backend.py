import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

from inspect_ai.log import (
    list_eval_logs,
    read_eval_log,
    read_eval_log_sample,
    read_eval_log_sample_summaries,
)

from tracelab.inspect_adapter.normalize import normalize_sample
from tracelab.models.domain import Experiment, Trajectory


class EvalBackend(Protocol):
    def discover(self, path: str) -> list[str]: ...
    def load_experiment(self, path: str, workspace_id: str) -> Experiment: ...
    def list_trajectories(self, experiment: Experiment) -> list[Trajectory]: ...
    def load_trajectory(self, trajectory: Trajectory, experiment: Experiment): ...
    def list_checkpoints(self, trajectory: Trajectory) -> dict: ...
    async def run_fork(self, request: dict): ...
    def open_native_view(self, experiment: Experiment) -> list[str]: ...


def stable_id(prefix: str, *parts) -> str:
    return prefix + "_" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:20]


class InspectBackend:
    version = version("inspect_ai")

    def discover(self, path: str) -> list[str]:
        root = Path(path).expanduser().resolve(strict=True)
        if root.is_file():
            if root.suffix not in (".eval", ".json"):
                raise ValueError("Choose an Inspect .eval file or logs directory")
            return [str(root)]
        return [str(x.name) for x in list_eval_logs(str(root), formats=["eval", "json"])]

    def load_experiment(self, path: str, workspace_id: str) -> Experiment:
        header = read_eval_log(path, header_only=True).model_dump(mode="json")
        spec = header["eval"]
        return Experiment(
            id=stable_id("exp", workspace_id, path),
            workspace_id=workspace_id,
            name=spec.get("task", Path(path).stem),
            source_path=path,
            task=spec.get("task"),
            dataset=(spec.get("dataset") or {}).get("name"),
            created_at=spec.get("created"),
            metadata={
                "inspect": header,
                "inspectVersion": self.version,
                "sourceFingerprint": self.fingerprint(path),
            },
        )

    @staticmethod
    def fingerprint(path: str):
        # mtime/size make re-index cheap. Full source and input hashes are recorded for derived jobs.
        from urllib.parse import unquote, urlparse

        local = unquote(urlparse(path).path) if path.startswith("file://") else path
        stat = Path(local).stat()
        return f"{stat.st_size}:{stat.st_mtime_ns}"

    def list_trajectories(self, experiment: Experiment, access_path=None) -> list[Trajectory]:
        items = []
        spec = experiment.metadata["inspect"]["eval"]
        for summary in read_eval_log_sample_summaries(access_path or experiment.source_path):
            raw = summary.model_dump(mode="json")
            sample_id = str(raw["id"])
            metadata = raw.get("metadata") or {}
            usage = list((raw.get("model_usage") or {}).values())
            input_tokens = sum(x.get("input_tokens", 0) for x in usage) if usage else None
            output_tokens = sum(x.get("output_tokens", 0) for x in usage) if usage else None
            items.append(
                Trajectory(
                    id=stable_id("traj", experiment.id, raw["id"], raw.get("epoch", 1)),
                    experiment_id=experiment.id,
                    sample_id=sample_id,
                    epoch=raw.get("epoch", 1),
                    model=spec.get("model"),
                    task=spec.get("task"),
                    condition=str(
                        metadata.get(
                            "condition", (spec.get("metadata") or {}).get("condition", "baseline")
                        )
                    ),
                    status="error" if raw.get("error") else "unknown",
                    started_at=raw.get("started_at"),
                    completed_at=raw.get("completed_at"),
                    duration_ms=raw["total_time"] * 1000
                    if raw.get("total_time") is not None
                    else None,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=(input_tokens or 0) + (output_tokens or 0) if usage else None,
                    scores=raw.get("scores") or {},
                    metadata={
                        "inspectSummary": raw,
                        "inspectSampleId": raw["id"],
                        "executionStatus": experiment.metadata["inspect"].get("status"),
                        "outcomeNote": "Execution completion is not evidence of task success.",
                    },
                )
            )
        return items

    def load_trajectory(self, trajectory: Trajectory, experiment: Experiment, access_path=None):
        sample = read_eval_log_sample(
            access_path or experiment.source_path,
            id=trajectory.metadata.get("inspectSampleId", trajectory.sample_id),
            epoch=trajectory.epoch or 1,
            resolve_attachments=True,
        ).model_dump(mode="json")
        events, sources = normalize_sample(trajectory.id, sample)
        trajectory.loaded = True
        trajectory.event_count = len(events)
        trajectory.started_at = sample.get("started_at")
        trajectory.completed_at = sample.get("completed_at")
        if trajectory.started_at and trajectory.completed_at:
            from datetime import datetime

            trajectory.duration_ms = (
                datetime.fromisoformat(trajectory.completed_at)
                - datetime.fromisoformat(trajectory.started_at)
            ).total_seconds() * 1000
        usage = list((sample.get("model_usage") or {}).values())
        trajectory.input_tokens = sum(x.get("input_tokens", 0) for x in usage) if usage else None
        trajectory.output_tokens = sum(x.get("output_tokens", 0) for x in usage) if usage else None
        trajectory.total_tokens = (
            (trajectory.input_tokens or 0) + (trajectory.output_tokens or 0) if usage else None
        )
        trajectory.scores = sample.get("scores") or trajectory.scores
        if sample.get("error"):
            trajectory.status = "error"
        return trajectory, events, sources

    def list_checkpoints(self, trajectory: Trajectory) -> dict:
        return {
            "contextOnly": True,
            "checkpointRestored": False,
            "reason": "This adapter cannot restore an arbitrary Inspect checkpoint as an independent intervention branch. A log checkpoint marker alone does not contain a restorable sandbox.",
            "inspectVersion": self.version,
        }

    async def run_fork(self, request: dict):
        from tracelab.inspect_adapter.replay import continue_context

        return await continue_context(**request)

    def open_native_view(self, experiment: Experiment) -> list[str]:
        return [
            "view",
            "--log-dir",
            str(Path(experiment.source_path.removeprefix("file://")).parent),
            "--host",
            "127.0.0.1",
        ]
