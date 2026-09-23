from collections.abc import Iterator
from typing import Any, Protocol

from pydantic import Field

from tracelab.models.domain import AppModel, SourceRef, Trajectory, TrajectoryEvent
from tracelab.sources.base import SourceProvider


class DetectionResult(AppModel):
    confidence: float = Field(ge=0, le=1)
    format: str
    reason: str


class ImportMetadata(AppModel):
    name: str
    format: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunReference(AppModel):
    source: SourceRef
    format: str
    id: str
    locator: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedTrajectory(AppModel):
    trajectory: Trajectory
    events: list[TrajectoryEvent]
    raw_records: list[dict] = Field(default_factory=list)


class TrajectoryImporter(Protocol):
    name: str

    def detect(self, source: SourceProvider, ref: SourceRef) -> DetectionResult: ...
    def inspect_metadata(self, source: SourceProvider, ref: SourceRef) -> ImportMetadata: ...
    def discover_runs(self, source: SourceProvider, ref: SourceRef) -> list[RunReference]: ...
    def load_trajectory(
        self, source: SourceProvider, run: RunReference
    ) -> NormalizedTrajectory: ...
    def iter_events(
        self, source: SourceProvider, run: RunReference, trajectory_id: str
    ) -> Iterator[TrajectoryEvent]: ...
