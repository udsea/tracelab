"""One read-only preparation path shared by preview and execution."""

import json
from dataclasses import dataclass, field

from tracelab.classifiers.runner import canonical_hash
from tracelab.forks.context import GENERATION_PARAMETERS, apply_interventions, context_messages
from tracelab.forks.replay import (
    POLICY,
    RecordedToolCatalog,
    ReplayResolver,
    ReplayTapeEntry,
    ReplayUnsupported,
    build_replay_tape,
    replay_plan_hash,
)
from tracelab.inspect_adapter.tool_catalog import extract_recorded_tool_catalog, tool_result_message
from tracelab.models.domain import Fork, ProviderSettings, Trajectory
from tracelab.sources.concurrency import blocking


@dataclass
class PreparedFork:
    fork: Fork
    parent: Trajectory
    source_event: dict
    edited_events: list
    appended_messages: list
    messages: list
    model: str
    provider: ProviderSettings
    generation_parameters: dict
    tool_catalog: RecordedToolCatalog | None = None
    replay_tape: tuple[ReplayTapeEntry, ...] = ()
    replay_support: dict = field(
        default_factory=lambda: {
            "supported": False,
            "reasonCode": None,
            "reason": "Single reply uses no tools.",
        }
    )
    input_hash: str = ""
    execution_hash: str = ""
    replay_plan_hash: str | None = None

    @property
    def execution_spec(self):
        return self.fork.execution_spec

    def execution_identity(self, parameters):
        return canonical_hash(
            {
                "inputHash": self.input_hash,
                "providerId": self.provider.id,
                "model": self.model,
                "parameters": parameters,
                "executionSpec": self.execution_spec.wire(),
                "toolCatalogHash": self.tool_catalog.canonical_hash if self.tool_catalog else None,
                "replayPlanHash": self.replay_plan_hash,
                "stubHashes": [canonical_hash(s.wire()) for s in self.execution_spec.tool_stubs],
            }
        )

    def preview(self):
        return {
            "sourceEventIndex": self.source_event["index"],
            "model": self.model,
            "provider": self.provider.wire(),
            "parameters": self.generation_parameters,
            "seedIncrementsByReplication": isinstance(self.generation_parameters.get("seed"), int),
            "replicationCount": self.fork.replication_count,
            "messages": self.messages,
            "inputHash": self.input_hash,
            "executionHash": self.execution_hash,
            "executionSpec": self.execution_spec.wire(),
            "contextCharacters": len(json.dumps(self.messages, ensure_ascii=False)),
            "replaySupport": self.replay_support,
            "toolCatalog": {
                "count": len(self.tool_catalog.tools),
                "hash": self.tool_catalog.canonical_hash,
                "names": [t.name for t in self.tool_catalog.tools],
            }
            if self.tool_catalog
            else None,
            "replayPlan": {
                "policy": POLICY,
                "entryCount": len(self.replay_tape),
                "hash": self.replay_plan_hash,
                "entries": [
                    {
                        k: getattr(e, attr)
                        for k, attr in (
                            ("ordinal", "ordinal"),
                            ("toolName", "tool_name"),
                            ("sourceCallEventId", "source_call_event_id"),
                            ("sourceResultEventId", "source_result_event_id"),
                            ("argumentsHash", "arguments_hash"),
                            ("resultHash", "result_hash"),
                        )
                    }
                    for e in self.replay_tape[:5]
                ],
            },
        }


async def prepare(runner, fork):
    if fork.fidelity != "context_only":
        raise ValueError("Checkpoint restoration is unavailable for this adapter")
    parent = Trajectory.model_validate(runner.db.get("trajectories", fork.source_trajectory_id))
    events = await runner.load_events(parent.id)
    return await blocking(prepare_loaded, runner, fork, parent, events)


def prepare_loaded(runner, fork, parent, events):
    source = next((e for e in events if e["id"] == fork.source_event_id), None)
    if not source:
        raise ValueError("Source event does not belong to source trajectory")
    edited, appended, config = apply_interventions(
        [e for e in events if e["index"] <= source["index"]], fork
    )
    model = config.get("model") or parent.model
    if not model:
        raise ValueError("A continuation model is required")
    provider = ProviderSettings.model_validate(
        runner.db.get("providers", config.get("provider", "openai"))
    )
    parameters = dict(config.get("parameters", {}))
    if set(parameters) - GENERATION_PARAMETERS:
        raise ValueError("Unsupported fork generation parameter")
    p = PreparedFork(fork, parent, source, edited, appended, [], model, provider, parameters)
    multi = fork.execution_spec.continuation == "multi_step"
    try:
        if parent.capabilities and not parent.capabilities.context_fork:
            raise ValueError(parent.capabilities.reason)
        p.messages = context_messages(edited, appended)
    except ValueError as exc:
        if not multi:
            raise
        p.replay_support = {
            "supported": False,
            "reasonCode": "context_reconstruction_unavailable",
            "reason": str(exc),
        }
    else:
        if multi:
            try:
                records = runner.db.list(
                    "source_records",
                    "id IN (SELECT data->'metadata'->>'sourceRecordId' FROM events WHERE trajectory_id = ?)",
                    [parent.id],
                    limit=1000000,
                )
                p.tool_catalog = extract_recorded_tool_catalog(events, records, source["index"])
                p.replay_tape = build_replay_tape(events, source["index"])
                # Validation creates an independent resolver; it never consumes a tape entry.
                ReplayResolver(p.replay_tape, fork.execution_spec)
                for stub in fork.execution_spec.tool_stubs:
                    tool_result_message("preview", stub.tool_name, stub.result, stub.error)
                for entry in p.replay_tape:
                    tool_result_message("preview", entry.tool_name, entry.result, entry.error)
                p.replay_plan_hash = replay_plan_hash(p.tool_catalog, p.replay_tape)
                p.replay_support = {
                    "supported": True,
                    "reasonCode": None,
                    "reason": "Exact sequential recorded observations are available; no environment or tools are restored.",
                }
            except ReplayUnsupported as exc:
                p.replay_support = {"supported": False, "reasonCode": exc.code, "reason": str(exc)}
    p.input_hash = canonical_hash(p.messages)
    p.execution_hash = p.execution_identity(parameters)
    return p
