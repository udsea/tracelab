from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AppModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    def wire(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


class Workspace(AppModel):
    id: str = Field(default_factory=lambda: uid("ws"))
    name: str
    sources: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
    opened_at: str = Field(default_factory=now)
    is_demo: bool = False


class SourceRef(AppModel):
    kind: Literal["local", "huggingface", "http"]
    uri: str
    revision: str | None = None
    size_bytes: int | None = None
    etag: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrajectoryCapabilities(AppModel):
    analyze: bool = True
    classify: bool = True
    segment: bool = True
    visualize: bool = True
    multi_agent_graph: bool = False
    artifacts: bool = False
    context_fork: bool = False
    checkpoint_fork: bool = False
    environment_fork: bool = False
    exact_replay: bool = False
    reason: str = "No verified replay integration for this source."


class Experiment(AppModel):
    id: str
    workspace_id: str
    name: str
    source_path: str
    source_type: str = "inspect"
    source_ref: SourceRef | None = None
    task: str | None = None
    dataset: str | None = None
    created_at: str | None = None
    imported_at: str = Field(default_factory=now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Trajectory(AppModel):
    id: str
    experiment_id: str
    sample_id: str
    epoch: int | None = None
    model: str | None = None
    task: str | None = None
    condition: str | None = None
    status: Literal["running", "success", "failure", "error", "cancelled", "unknown"] = "unknown"
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    scores: dict[str, Any] = Field(default_factory=dict)
    parent_trajectory_id: str | None = None
    fork_id: str | None = None
    event_count: int = 0
    loaded: bool = False
    source_ref: SourceRef | None = None
    capabilities: TrajectoryCapabilities | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolData(AppModel):
    name: str
    call_id: str | None = None
    arguments: Any = None
    result: Any = None
    error: str | None = None


EventType = Literal[
    "system",
    "user",
    "assistant",
    "reasoning",
    "tool_call",
    "tool_result",
    "environment",
    "score",
    "error",
    "checkpoint",
    "annotation",
    "other",
]


class TrajectoryEvent(AppModel):
    id: str
    trajectory_id: str
    index: int
    parent_event_ids: list[str] = Field(default_factory=list)
    timestamp: str | None = None
    type: EventType
    role: str | None = None
    content: str | None = None
    tool: ToolData | None = None
    token_usage: dict[str, int | None] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Segment(AppModel):
    id: str = Field(default_factory=lambda: uid("seg"))
    trajectory_id: str
    start_event: int = Field(ge=0)
    end_event: int = Field(ge=0)
    label: str = Field(min_length=1)
    summary: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)
    parent_id: str | None = None
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_event < self.start_event:
            raise ValueError("Segment end must follow its start")
        return self


class Annotation(AppModel):
    id: str = Field(default_factory=lambda: uid("ann"))
    trajectory_id: str
    start_event_index: int = Field(ge=0)
    end_event_index: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=120)
    note: str | None = None
    created_at: str = Field(default_factory=now)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_event_index < self.start_event_index:
            raise ValueError("Annotation end must follow its start")
        return self


class ClassifierDefinition(AppModel):
    version: int = Field(default=1, ge=1)
    previous_id: str | None = None
    id: str = Field(default_factory=lambda: uid("clf"))
    workspace_id: str | None = None
    name: str = Field(min_length=1)
    description: str = ""
    prompt: str = Field(min_length=1)
    model: str
    provider: str
    scope: Literal["event", "window", "trajectory"] = "window"
    window_size: int = Field(default=20, ge=1, le=10000)
    stride: int = Field(default=5, ge=1, le=10000)
    labels: list[str] = Field(default_factory=list)
    return_score: bool = True
    return_rationale: bool = True
    return_evidence: bool = True
    output_schema: dict[str, Any] = Field(default_factory=dict)
    generation_parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now)
    is_template: bool = False


class ClassifierOutput(AppModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")
    confidence: float | None = Field(default=None, ge=0, le=1)
    observability: Literal["explicit", "behavioral", "mixed", "none"] | None = None
    counterevidence_event_ids: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    # Provider JSON uses snake_case; application models use camelCase on the wire.
    label: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    rationale: str | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)


class ClassifierResult(AppModel):
    id: str = Field(default_factory=lambda: uid("res"))
    classifier_id: str
    run_id: str
    trajectory_id: str
    start_event_index: int
    end_event_index: int
    output: ClassifierOutput | None = None
    error: str | None = None
    cache_key: str
    cached: bool = False
    created_at: str = Field(default_factory=now)
    provenance: dict = Field(default_factory=dict)


class RemoveEvent(AppModel):
    type: Literal["remove_event"]
    event_id: str


class ReplaceContent(AppModel):
    type: Literal["replace_content"]
    event_id: str
    content: str


class ReplaceToolResult(AppModel):
    type: Literal["replace_tool_result"]
    event_id: str
    value: Any


class AppendMessage(AppModel):
    type: Literal["append_message"]
    role: Literal["user", "assistant", "system"]
    content: str


class SystemOverride(AppModel):
    type: Literal["system_prompt_override"]
    content: str


class ModelOverride(AppModel):
    type: Literal["model_override"]
    model: str


class GenerationOverride(AppModel):
    type: Literal["generation_override"]
    parameters: dict[str, Any]


Intervention = Annotated[
    RemoveEvent
    | ReplaceContent
    | ReplaceToolResult
    | AppendMessage
    | SystemOverride
    | ModelOverride
    | GenerationOverride,
    Field(discriminator="type"),
]


class Fork(AppModel):
    id: str = Field(default_factory=lambda: uid("fork"))
    source_trajectory_id: str
    source_event_id: str
    created_at: str = Field(default_factory=now)
    fidelity: Literal["context_only", "checkpoint_restored"] = "context_only"
    interventions: list[Intervention] = Field(default_factory=list)
    model_overrides: dict[str, Any] = Field(default_factory=dict)
    replication_count: int = Field(default=1, ge=1, le=100)
    child_trajectory_ids: list[str] = Field(default_factory=list)
    status: Literal["configured", "running", "complete", "failed"] = "configured"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Job(AppModel):
    id: str = Field(default_factory=lambda: uid("job"))
    kind: Literal["import", "classifier", "fork", "segmentation", "index", "analysis"]
    name: str
    status: Literal["queued", "running", "complete", "failed", "cancelled"] = "queued"
    completed: int = 0
    total: int = 0
    concurrency: int = 1
    created_at: str = Field(default_factory=now)
    completed_at: str | None = None
    error: str | None = None
    logs: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ProviderSettings(AppModel):
    id: str
    name: str
    kind: Literal["openai_compatible", "anthropic"]
    base_url: str
    api_key_env: str
    default_model: str = ""
