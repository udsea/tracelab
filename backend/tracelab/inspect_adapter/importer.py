from contextlib import contextmanager

from inspect_ai.log import read_eval_log

from tracelab.importers.base import (
    DetectionResult,
    ImportMetadata,
    NormalizedTrajectory,
    RunReference,
)
from tracelab.inspect_adapter.backend import InspectBackend
from tracelab.models.domain import Experiment, Trajectory
from tracelab.sources.filesystem import TraceLabFileSystem


@contextmanager
def inspect_access(source, ref):
    if ref.kind == "local":
        yield ref.uri
    else:
        # Inspect supports fsspec URLs; this bridge adds persistent range caching and accounting.
        uri = TraceLabFileSystem.bind(source, ref)
        try:
            yield uri
        finally:
            TraceLabFileSystem.release(uri)


class InspectImporter:
    name = "inspect"

    def __init__(self):
        self.adapter = InspectBackend()

    def detect(self, source, ref):
        raw = source.read_range(ref, 0, min(256, ref.size_bytes or 256))
        possible = raw.startswith(b"PK") or b'"eval"' in raw
        if possible:
            try:
                with inspect_access(source, ref) as uri:
                    header = read_eval_log(
                        uri, header_only=True, format="eval" if raw.startswith(b"PK") else "json"
                    )
                if header.eval.task:
                    return DetectionResult(
                        confidence=0.99,
                        format=self.name,
                        reason="Validated by the public Inspect log reader",
                    )
            except Exception as exc:
                return DetectionResult(
                    confidence=0,
                    format=self.name,
                    reason=f"Not a readable Inspect log: {type(exc).__name__}",
                )
        return DetectionResult(
            confidence=0, format=self.name, reason="No Inspect container/header signature"
        )

    def inspect_metadata(self, source, ref):
        with inspect_access(source, ref) as uri:
            header = read_eval_log(uri, header_only=True).model_dump(mode="json")
        return ImportMetadata(
            name=header["eval"]["task"],
            format=self.name,
            metadata={"inspect": header, "inspectVersion": self.adapter.version},
        )

    def discover_runs(self, source, ref):
        info = self.inspect_metadata(source, ref)
        experiment = Experiment(
            id="pending",
            workspace_id="",
            name=info.name,
            source_path=ref.uri,
            source_ref=ref,
            metadata=info.metadata,
        )
        with inspect_access(source, ref) as uri:
            items = self.adapter.list_trajectories(experiment, uri)
        return [
            RunReference(
                source=ref,
                format=self.name,
                id=f"{item.sample_id}:{item.epoch}",
                metadata={"trajectory": item.wire()},
            )
            for item in items
        ]

    def load_trajectory(self, source, run):
        trajectory = Trajectory.model_validate(run.metadata["trajectory"])
        experiment = Experiment.model_validate(run.metadata["experiment"])
        with inspect_access(source, run.source) as uri:
            trajectory, events, raw = self.adapter.load_trajectory(trajectory, experiment, uri)
        return NormalizedTrajectory(trajectory=trajectory, events=events, raw_records=raw)
