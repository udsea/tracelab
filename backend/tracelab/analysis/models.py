"""Derived research objects. Source events and existing classifier records stay immutable."""

from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from tracelab.models.domain import AppModel, now, uid


class SemanticEvent(AppModel):
    event_id: str
    index: int
    agent_id: str | None = None
    type: str
    summary: str
    presentation_class: Literal["semantic", "runtime", "opaque"] = "semantic"
    reasoning_visibility: (
        Literal["plaintext", "summary", "encrypted", "redacted", "opaque"] | None
    ) = None
    model_call_id: str | None = None
    tool_name: str | None = None
    tool_arguments_summary: str | None = None
    tool_result_summary: str | None = None
    tool_success: bool | None = None
    error: str | None = None
    timestamp: str | None = None
    duration_ms: float | None = None
    parent_ids: list[str] = Field(default_factory=list)
    artifacts: list[Any] = Field(default_factory=list)
    environment_effects: list[Any] = Field(default_factory=list)
    model_call: bool = False
    metadata: dict = Field(default_factory=dict)


class OutlineNode(AppModel):
    id: str = Field(default_factory=lambda: uid("outline"))
    trajectory_id: str
    kind: Literal["segment", "episode", "activity", "moment"]
    start_event_index: int = Field(ge=0)
    end_event_index: int = Field(ge=0)
    label: str
    summary: str = ""
    parent_id: str | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_event_index < self.start_event_index:
            raise ValueError("Outline range is reversed")
        if self.kind == "moment" and self.start_event_index != self.end_event_index:
            raise ValueError("Moments reference one event")
        return self


class ArtifactRef(AppModel):
    id: str = Field(default_factory=lambda: uid("artifact"))
    trajectory_id: str
    uri: str
    format: Literal["parquet", "zarr", "npz", "safetensors", "json", "custom"]
    metadata: dict = Field(default_factory=dict)


class ModelInternalSource(AppModel):
    id: str = Field(default_factory=lambda: uid("internal"))
    trajectory_id: str
    artifact_ids: list[str]
    measurement: Literal["probe", "sae", "logit", "activation", "custom"]
    model: str | None = None
    metadata: dict = Field(default_factory=dict)


class AnalysisSignal(AppModel):
    id: str = Field(default_factory=lambda: uid("signal"))
    trajectory_id: str
    name: str
    source_type: Literal[
        "llm",
        "rule",
        "statistical",
        "contrastive",
        "intervention",
        "environment",
        "graph",
        "probe",
        "sae",
        "logit",
        "human",
        "custom",
    ]
    channel: Literal["BLACK_BOX", "GRAY_BOX", "WHITE_BOX"] = "BLACK_BOX"
    start_event_index: int = Field(ge=0)
    end_event_index: int = Field(ge=0)
    score: float | None = Field(default=None, allow_inf_nan=False)
    label: str | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)
    artifact_ref: str | None = None
    provenance: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_event_index < self.start_event_index:
            raise ValueError("Signal range is reversed")
        return self


class DetectorDefinition(AppModel):
    id: str = Field(default_factory=lambda: uid("detector"))
    name: str
    detector_type: Literal["rule", "statistical", "contrastive"]
    version: int = Field(default=1, ge=1)
    previous_id: str | None = None
    parameters: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now)


class Detector(Protocol):
    detector_type: str

    async def run(self, trajectory_ids: list[str], config: dict) -> list[AnalysisSignal]: ...
