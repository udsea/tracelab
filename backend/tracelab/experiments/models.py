"""Concrete experiment designs and durable scheduling units; no outcomes or scores."""

from typing import Literal

from pydantic import Field, model_validator

from tracelab.models.domain import AppModel, ForkExecutionSpec, Intervention, now, uid


class ForkExperimentArm(AppModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: Literal["control", "treatment"]
    description: str = ""


class ForkExperimentCaseArm(AppModel):
    arm_id: str
    interventions: list[Intervention] = Field(default_factory=list)


class ForkExperimentCase(AppModel):
    id: str = Field(min_length=1)
    source_trajectory_id: str
    source_event_id: str
    label: str | None = None
    arms: list[ForkExperimentCaseArm]


class ForkExperimentSpec(AppModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    arms: list[ForkExperimentArm] = Field(min_length=1, max_length=8)
    cases: list[ForkExperimentCase] = Field(min_length=1, max_length=200)
    execution_spec: ForkExecutionSpec = Field(default_factory=ForkExecutionSpec)
    model_overrides: dict = Field(default_factory=dict)
    replication_count: int = Field(default=1, ge=1, le=100)
    schedule_policy: Literal["paired_interleaved_v1"] = "paired_interleaved_v1"

    @model_validator(mode="after")
    def concrete_design(self):
        arms = {a.id for a in self.arms}
        if len(arms) != len(self.arms) or len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("Case and arm IDs must be unique")
        for case in self.cases:
            if len(case.arms) != len(arms) or {a.arm_id for a in case.arms} != arms:
                raise ValueError("Every case must reference every arm exactly once")
        if len(self.cases) * len(arms) * self.replication_count > 2000:
            raise ValueError("At most 2000 trials per fork experiment")
        if set(self.model_overrides) - {"provider", "model", "parameters"}:
            raise ValueError(
                "Use provider ID, model and generation parameters; credentials belong in provider settings"
            )
        return self


class ForkExperiment(ForkExperimentSpec):
    id: str = Field(default_factory=lambda: uid("fexp"))
    created_at: str = Field(default_factory=now)
    status: Literal["configured", "running", "complete", "partial", "cancelled", "failed"] = (
        "configured"
    )
    spec_hash: str
    fork_ids: list[str] = Field(default_factory=list)
    trial_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class ForkTrial(AppModel):
    id: str = Field(default_factory=lambda: uid("trial"))
    experiment_id: str
    case_id: str
    arm_id: str
    fork_id: str
    replication_index: int
    pair_key: str
    schedule_ordinal: int
    status: Literal["pending", "running", "complete", "error", "cancelled", "interrupted"] = (
        "pending"
    )
    child_trajectory_id: str | None = None
    requested_seed: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    metadata: dict = Field(default_factory=dict)
