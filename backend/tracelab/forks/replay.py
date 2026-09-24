"""Exact observation resolution. No provider, filesystem, shell or tool execution here."""

import copy
import hashlib
import json
from collections import defaultdict
from typing import Any, Literal

from pydantic import ConfigDict, Field

from tracelab.classifiers.runner import canonical_hash
from tracelab.models.domain import AppModel, ForkExecutionSpec, now, uid

POLICY = "strict_sequential_exact_v1"
STUB_POLICY = "exact_stub_v1"


class ReplayUnsupported(ValueError):
    def __init__(self, code, reason):
        self.code = code
        super().__init__(reason)


def canonical_tool_arguments(value: Any) -> str:
    # Only a top-level JSON object/array string denotes encoded structured arguments.
    # Strings inside a structure and all other strings remain byte-for-byte text.
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                value = parsed
        except ValueError:
            pass
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def arguments_hash(value):
    return hashlib.sha256(canonical_tool_arguments(value).encode()).hexdigest()


class RecordedToolDefinition(AppModel):
    name: str
    description: str | None = None
    parameters_schema: dict
    source_record_id: str


class RecordedToolCatalog(AppModel):
    tools: list[RecordedToolDefinition]
    canonical_hash: str
    source_record_ids: list[str]


class ReplayTapeEntry(AppModel):
    model_config = ConfigDict(frozen=True)
    ordinal: int
    source_call_event_id: str
    source_result_event_id: str
    source_call_index: int
    source_result_index: int
    tool_name: str
    arguments: Any
    arguments_hash: str
    result: Any
    result_hash: str
    error: Any = None
    source_call_record_id: str | None = None
    source_result_record_id: str | None = None


ToolResultOrigin = Literal["recorded_replay", "stub"]
TerminationReason = Literal[
    "assistant_completed",
    "max_model_steps",
    "max_tool_calls",
    "replay_tape_exhausted",
    "unmatched_tool_call",
    "missing_tool_catalog",
    "unsupported_tool_result",
    "tool_resolution_error",
    "model_error",
    "cancelled",
]


class ToolResolution(AppModel):
    id: str = Field(default_factory=lambda: uid("resolution"))
    fork_id: str
    trajectory_id: str
    model_step: int
    generated_call_id: str
    generated_call_event_id: str
    generated_result_event_id: str | None = None
    tool_name: str
    arguments_hash: str
    origin: ToolResultOrigin
    match_policy: str
    replay_ordinal: int | None = None
    matched_source_call_event_id: str | None = None
    matched_source_result_event_id: str | None = None
    stub_id: str | None = None
    created_at: str = Field(default_factory=now)


def build_replay_tape(events, source_index) -> tuple[ReplayTapeEntry, ...]:
    calls, results = defaultdict(list), defaultdict(list)
    for event in events:
        if event["type"] in ("tool_call", "tool_result"):
            target = calls if event["type"] == "tool_call" else results
            target[(event.get("tool") or {}).get("callId")].append(event)
    future = [e for e in events if e["type"] == "tool_call" and e["index"] > source_index]
    if not future:
        raise ReplayUnsupported(
            "no_future_tool_calls", "No recorded tool calls follow this fork point."
        )
    for event in events:
        if event["type"] == "tool_result" and event["index"] > source_index:
            cid = (event.get("tool") or {}).get("callId")
            if not cid or len(calls.get(cid, [])) != 1:
                raise ReplayUnsupported(
                    "ambiguous_tool_result", "A future recorded result has no unique source call."
                )
    tape = []
    for call in future:
        tool = call.get("tool") or {}
        cid = tool.get("callId")
        matches = results.get(cid, [])
        if not cid or len(calls[cid]) != 1 or len(matches) != 1:
            raise ReplayUnsupported(
                "ambiguous_tool_result",
                "Future calls require unique recorded call/result IDs; replay cannot skip an ambiguous action.",
            )
        result = matches[0]
        rt = result.get("tool") or {}
        if result["index"] <= call["index"] or rt.get("name") != tool.get("name"):
            raise ReplayUnsupported(
                "ambiguous_tool_result",
                "Recorded call/result identity or ordering is inconsistent.",
            )
        meta = result.get("metadata") or {}
        error = (
            meta.get("toolError")
            or (meta.get("nativeMessage") or {}).get("error")
            or rt.get("error")
        )
        value = copy.deepcopy(rt.get("result"))
        tape.append(
            ReplayTapeEntry(
                ordinal=len(tape),
                source_call_event_id=call["id"],
                source_result_event_id=result["id"],
                source_call_index=call["index"],
                source_result_index=result["index"],
                tool_name=tool["name"],
                arguments=copy.deepcopy(tool.get("arguments")),
                arguments_hash=arguments_hash(tool.get("arguments")),
                result=value,
                result_hash=canonical_hash({"result": value, "error": error}),
                error=copy.deepcopy(error),
                source_call_record_id=call.get("metadata", {}).get("sourceRecordId"),
                source_result_record_id=meta.get("sourceRecordId"),
            )
        )
    return tuple(tape)


def replay_plan_hash(catalog, tape):
    return canonical_hash(
        {
            "policy": POLICY,
            "toolCatalogHash": catalog.canonical_hash,
            "entries": [
                {
                    k: getattr(e, attr)
                    for k, attr in (
                        ("sourceCallEventId", "source_call_event_id"),
                        ("sourceResultEventId", "source_result_event_id"),
                        ("toolName", "tool_name"),
                        ("argumentsHash", "arguments_hash"),
                        ("resultHash", "result_hash"),
                    )
                }
                for e in tape
            ],
        }
    )


class ReplayResolver:
    def __init__(self, tape, spec: ForkExecutionSpec):
        self.tape, self.spec = tape, spec
        self.keys = [(e.tool_name, canonical_tool_arguments(e.arguments)) for e in tape]
        self.cursor = 0
        self.diverged_by_stub = False
        self.stubs = {}
        for stub in spec.tool_stubs:
            key = (stub.tool_name, canonical_tool_arguments(stub.arguments))
            if key in self.stubs:
                raise ValueError("Duplicate exact stub matches are ambiguous")
            self.stubs[key] = stub

    def resolve(self, name, arguments):
        key = (name, canonical_tool_arguments(arguments))
        if not self.diverged_by_stub and self.cursor < len(self.tape):
            expected = self.tape[self.cursor]
            if key == self.keys[self.cursor]:
                self.cursor += 1
                return "recorded_replay", expected
        if self.spec.unmatched_tool_policy == "stub" and key in self.stubs:
            self.diverged_by_stub = True
            return "stub", self.stubs[key]
        reason = (
            "unmatched_tool_call"
            if self.diverged_by_stub or self.cursor < len(self.tape)
            else "replay_tape_exhausted"
        )
        raise ReplayUnsupported(
            reason,
            "Generated tool call does not match the next eligible recorded observation or an exact stub.",
        )
