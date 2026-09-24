"""One replication's counters, persistence and observation resolver; no tool execution."""

import copy

from tracelab.forks.replay import (
    POLICY,
    STUB_POLICY,
    ReplayResolver,
    ReplayUnsupported,
    TerminationReason,
    ToolResolution,
    arguments_hash,
)
from tracelab.inspect_adapter.normalize import normalize_sample
from tracelab.inspect_adapter.tool_catalog import tool_result_message
from tracelab.models.domain import now

MODE = "multi_step_recorded_replay"
NOTE = "Recorded tool outputs were reused without restoring or executing the source environment."


class ReplayExecution:
    def __init__(self, db, trajectory, prepared):
        self.db, self.trajectory, self.prepared = db, trajectory, prepared
        self.resolver = ReplayResolver(prepared.replay_tape, prepared.execution_spec)
        self.model_steps = self.tool_calls = self.replayed = self.stubbed = 0
        self.termination: TerminationReason | None = None
        self.usage = []

    def save(self):
        t = self.trajectory
        t.metadata.update(
            modelSteps=self.model_steps,
            toolCalls=self.tool_calls,
            replayedToolCalls=self.replayed,
            stubbedToolCalls=self.stubbed,
            replayCursorFinal=self.resolver.cursor,
            replayState="diverged_by_stub" if self.resolver.diverged_by_stub else "recorded",
            terminationReason=self.termination,
        )
        for field, key in (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            # A missing report makes the continuation total unknown, not a fabricated zero.
            setattr(
                t,
                field,
                sum(u[key] for u in self.usage)
                if len(self.usage) == self.model_steps
                and self.usage
                and all(u.get(key) is not None for u in self.usage)
                else None,
            )
        self.db.put("trajectories", t)

    def start_step(self):
        self.model_steps += 1
        self.save()

    def append(self, event, metadata=None, parents=None):
        t = self.trajectory
        event.id = f"{t.id}:e{t.event_count}"
        event.index = t.event_count
        event.trajectory_id = t.id
        event.parent_event_ids = parents or (
            [f"{t.id}:e{t.event_count - 1}"] if t.event_count else []
        )
        event.metadata.update(
            forkId=self.prepared.fork.id,
            branchGenerated=True,
            modelStep=self.model_steps,
            modelCallId=f"{t.id}:model:{self.model_steps}",
            executionMode=MODE,
        )
        event.metadata.update(metadata or {})
        self.db.put("events", event)
        t.event_count += 1
        return event

    def on_output(self, output, raw_model=None):
        """Persist the genuine generated output, then resolve calls in generated order."""
        self.usage.append(output.get("usage") or {})
        choices = output.get("choices") or []
        if not choices or not choices[0].get("message"):
            raise ValueError("Model returned no selected assistant message")
        message = choices[0]["message"]
        generated, sources = normalize_sample(
            f"{self.trajectory.id}:step{self.model_steps}",
            {"messages": [message], "output": output},
        )
        for source in sources:
            source["trajectoryId"] = self.trajectory.id
            if raw_model is not None and source["id"].endswith(":message0"):
                source["raw"] = copy.deepcopy(raw_model)
        self.db.put_many("source_records", sources)
        calls = [e for e in generated if e.type == "tool_call"]
        if generated and output.get("usage"):
            generated[0].token_usage = {
                "input": output["usage"].get("input_tokens"),
                "output": output["usage"].get("output_tokens"),
            }
        call_ids = [e.tool.call_id for e in calls]
        if len(set(call_ids)) != len(call_ids) or any(not cid for cid in call_ids):
            self.termination = "tool_resolution_error"
            self.trajectory.metadata["terminationDetail"] = (
                "Generated call IDs must be nonempty and unique within a model output."
            )

        self.tool_calls += len(
            calls
        )  # All generated calls, including unresolved calls, are observations.
        prior_calls = self.tool_calls - len(calls)
        # One generation emits every block/call before observing any tool result.
        # Keep normalized order; append mutates the collected calls to persisted IDs.
        for event in generated:
            self.append(event)
        results = []
        for ordinal, call in enumerate(calls, 1):
            if self.termination:
                break  # All emitted calls are persisted, including unresolved ones.
            if prior_calls + ordinal > self.prepared.execution_spec.max_tool_calls:
                self.termination = "max_tool_calls"
                continue
            raw_call = (message.get("tool_calls") or [])[ordinal - 1]
            if raw_call.get("parse_error") or raw_call.get("type", "function") != "function":
                self.termination = "tool_resolution_error"
                self.trajectory.metadata["terminationDetail"] = (
                    "Generated call arguments could not be parsed, or the call is not a supported function call."
                )
                continue
            tool = call.tool
            try:
                if not tool.call_id:
                    raise ReplayUnsupported(
                        "tool_resolution_error", "Generated tool call has no ID"
                    )
                origin, matched = self.resolver.resolve(tool.name, tool.arguments)
                result = tool_result_message(tool.call_id, tool.name, matched.result, matched.error)
                resolution = ToolResolution(
                    fork_id=self.prepared.fork.id,
                    trajectory_id=self.trajectory.id,
                    model_step=self.model_steps,
                    generated_call_id=tool.call_id,
                    generated_call_event_id=call.id,
                    tool_name=tool.name,
                    arguments_hash=arguments_hash(tool.arguments),
                    origin=origin,
                    match_policy=POLICY if origin == "recorded_replay" else STUB_POLICY,
                )
                meta = {
                    "toolResultOrigin": origin,
                    "toolResolutionId": resolution.id,
                    "matchPolicy": resolution.match_policy,
                }
                if origin == "recorded_replay":
                    resolution.replay_ordinal = matched.ordinal
                    resolution.matched_source_call_event_id = matched.source_call_event_id
                    resolution.matched_source_result_event_id = matched.source_result_event_id
                    meta.update(
                        matchedSourceTrajectoryId=self.prepared.parent.id,
                        matchedSourceCallEventId=matched.source_call_event_id,
                        matchedSourceResultEventId=matched.source_result_event_id,
                        matchedSourceCallIndex=matched.source_call_index,
                        matchedSourceResultIndex=matched.source_result_index,
                        replayOrdinal=matched.ordinal,
                    )
                else:
                    resolution.stub_id = matched.id
                    meta.update(stubId=matched.id, replayState="diverged_by_stub", synthetic=True)
                events, records = normalize_sample(resolution.id, {"messages": [result]})
                for record in records:
                    record["trajectoryId"] = self.trajectory.id
                    record["raw"] = {
                        "type": "tracelab_tool_replay",
                        "origin": origin,
                        **meta,
                        "message": copy.deepcopy(result),
                    }
                self.db.put_many("source_records", records)
                result_event = self.append(events[0], meta, [call.id])
                resolution.generated_result_event_id = result_event.id
                self.db.put("tool_resolutions", resolution)
                results.append(result)
                if origin == "recorded_replay":
                    self.replayed += 1
                else:
                    self.stubbed += 1
            except ReplayUnsupported as exc:
                self.termination = exc.code
                self.trajectory.metadata["terminationDetail"] = str(exc)
        if not calls:
            self.termination = "assistant_completed"
        elif (
            not self.termination
            and self.model_steps >= self.prepared.execution_spec.max_model_steps
        ):
            self.termination = "max_model_steps"
        self.save()
        return results

    def finish(self, reason=None):
        self.termination = reason or self.termination or "max_model_steps"
        t = self.trajectory
        if self.termination == "cancelled":
            t.status, status = "cancelled", "cancelled"
        elif self.termination in ("model_error", "tool_resolution_error"):
            t.status, status = "error", "error"
        else:
            t.status = "unknown"
            status = (
                "complete"
                if self.termination == "assistant_completed"
                else "bounded"
                if self.termination in ("max_model_steps", "max_tool_calls")
                else "policy_terminated"
            )
        t.metadata["executionStatus"] = status
        t.completed_at = now()
        self.save()
