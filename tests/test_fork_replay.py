import asyncio
import copy
import json

import pytest
from tracelab.forks.replay import (
    ReplayResolver,
    ReplayUnsupported,
    arguments_hash,
    build_replay_tape,
    canonical_tool_arguments,
)
from tracelab.inspect_adapter.normalize import normalize_sample
from tracelab.models.domain import Fork, ForkExecutionSpec, Job, ToolStub, Trajectory

SCHEMAS = [
    {
        "name": name,
        "description": name,
        "parameters": {
            "type": "object",
            "properties": {key: {"type": "string"}},
            "required": [key],
        },
    }
    for name, key in [("read_file", "path"), ("bash", "command")]
]
SPEC = {"continuation": "multi_step", "toolPolicy": "recorded_replay"}


def output(*calls, text="thinking", usage=True):
    value = {
        "model": "mockllm/model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "reasoning", "reasoning": text}
                        if calls
                        else {"type": "text", "text": text}
                    ],
                    "tool_calls": [
                        {"id": cid, "function": name, "arguments": args, "type": "function"}
                        for cid, name, args in calls
                    ],
                },
                "stop_reason": "tool_calls" if calls else "stop",
            }
        ],
    }
    if usage:
        value["usage"] = {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}
    return value


def source_sample():
    return {
        "events": [
            {
                "event": "model",
                "tools": SCHEMAS,
                "input": [{"role": "user", "content": "Task"}],
                "output": output(("p1", "read_file", {"path": "a.txt"})),
            },
            {
                "event": "tool",
                "id": "p1",
                "function": "read_file",
                "arguments": {"path": "a.txt"},
                "result": "alpha",
            },
            {
                "event": "model",
                "tools": SCHEMAS,
                "input": [],
                "output": output(("p2", "bash", {"command": "pytest -q"})),
            },
            {
                "event": "tool",
                "id": "p2",
                "function": "bash",
                "arguments": {"command": "pytest -q"},
                "result": "2 passed",
            },
            {"event": "model", "tools": SCHEMAS, "input": [], "output": output(text="Done")},
        ]
    }


async def setup(service, outputs=None, spec=None, replications=1):
    events, records = normalize_sample("t", source_sample())
    service.db.put(
        "trajectories",
        Trajectory(
            id="t",
            experiment_id="exp",
            sample_id="1",
            model="mock-model",
            loaded=True,
            event_count=len(events),
            status="success",
            scores={"original": 1},
        ),
    )
    service.db.put_many("events", events)
    service.db.put_many("source_records", records)
    fork = Fork(
        source_trajectory_id="t",
        source_event_id=events[0].id,
        execution_spec=spec or SPEC,
        replication_count=replications,
        model_overrides={"provider": "local", "model": "mock-model", "parameters": {"seed": 7}},
    )
    seen = []
    if outputs is not None:

        async def fake(request):
            execution = request["execution"]
            for value in outputs:
                if execution.termination:
                    break
                await asyncio.sleep(0)
                execution.start_step()
                if isinstance(value, BaseException):
                    raise value
                seen.append(execution.on_output(copy.deepcopy(value)))
            return {"sample": {}, "logPath": "local-test-log"}

        service.adapter.run_fork = fake
    return fork, events, records, seen


async def run(service, outputs, spec=None, replications=1):
    fork, events, records, seen = await setup(service, outputs, spec, replications)
    await service.forks.run(Job(kind="fork", name="test"), fork)
    child = service.db.get("trajectories", fork.child_trajectory_ids[0])
    return fork, child, await service.load_events(child["id"]), seen


def test_defaults_and_old_forks():
    f = Fork(source_trajectory_id="t", source_event_id="e")
    assert f.execution_spec.continuation == "single_turn"
    assert f.execution_spec.tool_policy == "disabled"
    assert Fork.model_validate(f.wire()).execution_spec == f.execution_spec


@pytest.mark.parametrize(
    "patch",
    [
        {"environment": "live"},
        {"scoring": "rerun"},
        {"toolPolicy": "live"},
        {"continuation": "multi_step"},
        {**SPEC, "unmatchedToolPolicy": "simulate"},
        {**SPEC, "toolPolicy": "stubbed"},
        {**SPEC, "toolPolicy": "simulated"},
        {**SPEC, "maxModelSteps": 0},
        {**SPEC, "maxToolCalls": 0},
        {"unmatchedToolPolicy": "stub"},
    ],
)
def test_unsupported_specs_fail(patch):
    with pytest.raises(ValueError):
        ForkExecutionSpec.model_validate(patch)


@pytest.mark.parametrize(
    "a,b,equal",
    [
        ({"b": 2, "a": 1}, {"a": 1, "b": 2}, True),
        ('{"b":2,"a":1}', {"a": 1, "b": 2}, True),
        ([1, 2], [2, 1], False),
        ("pytest -q", " pytest -q ", False),
        ({"path": "a/../b"}, {"path": "b"}, False),
        (True, 1, False),
        ("1", 1, False),
        (None, "null", False),
        ({"x": '{"a":1}'}, {"x": {"a": 1}}, False),
    ],
)
def test_argument_rules(a, b, equal):
    assert (canonical_tool_arguments(a) == canonical_tool_arguments(b)) is equal
    assert (arguments_hash(a) == arguments_hash(b)) is equal


def test_exact_tape_and_no_search_ahead():
    events, _ = normalize_sample("t", source_sample())
    tape = build_replay_tape([e.wire() for e in events], 0)
    r = ReplayResolver(tape, ForkExecutionSpec.model_validate(SPEC))
    with pytest.raises(ReplayUnsupported, match="does not match"):
        r.resolve("bash", {"command": "pytest -q"})
    assert r.cursor == 0
    assert r.resolve("read_file", '{"path":"a.txt"}')[1].result == "alpha"
    assert r.resolve("bash", {"command": "pytest -q"})[1].result == "2 passed"
    with pytest.raises(ReplayUnsupported) as exc:
        r.resolve("bash", {"command": "pytest -q"})
    assert exc.value.code == "replay_tape_exhausted"


def test_repeated_identical_calls_consume_distinct_observations():
    sample = source_sample()
    sample["events"][2]["output"] = output(("p2", "read_file", {"path": "a.txt"}))
    sample["events"][3].update(function="read_file", arguments={"path": "a.txt"}, result="beta")
    events, _ = normalize_sample("t", sample)
    r = ReplayResolver(
        build_replay_tape([e.wire() for e in events], 0), ForkExecutionSpec.model_validate(SPEC)
    )
    assert [r.resolve("read_file", {"path": "a.txt"})[1].result for _ in range(2)] == [
        "alpha",
        "beta",
    ]


async def test_three_steps_provenance_usage_prefix_and_restart(service):
    fork, child, events, seen = await run(
        service,
        [
            output(("child1", "read_file", {"path": "a.txt"})),
            output(("child2", "bash", {"command": "pytest -q"})),
            output(text="Done."),
        ],
        replications=2,
    )
    m = child["metadata"]
    assert (m["modelSteps"], m["toolCalls"], m["replayedToolCalls"], m["stubbedToolCalls"]) == (
        3,
        2,
        2,
        0,
    )
    assert m["terminationReason"] == "assistant_completed" and m["executionStatus"] == "complete"
    assert child["status"] == "unknown" and child["scores"] == {}
    assert (child["inputTokens"], child["outputTokens"], child["totalTokens"]) == (30, 9, 39)
    assert [e["type"] for e in events] == [
        "user",
        "reasoning",
        "tool_call",
        "tool_result",
        "reasoning",
        "tool_call",
        "tool_result",
        "assistant",
    ]
    assert seen[0][0]["tool_call_id"] == "child1"
    resolutions = service.db.list("tool_resolutions", "trajectory_id=?", [child["id"]])
    assert len(resolutions) == 2
    assert resolutions[0]["matchedSourceCallEventId"].startswith("t:e")
    for event in events[1:]:
        assert event["metadata"]["branchGenerated"]
        assert event["metadata"]["modelCallId"].endswith(str(event["metadata"]["modelStep"]))
    result_event = next(e for e in events if e["type"] == "tool_result")
    raw = await service.dispatch("events.raw", {"id": result_event["id"]})
    assert raw["raw"]["type"] == "tracelab_tool_replay"
    assert raw["raw"]["origin"] == "recorded_replay"
    assert service.db.get("trajectories", "t")["scores"] == {"original": 1}
    assert [
        service.db.get("trajectories", tid)["metadata"]["parameters"]["seed"]
        for tid in fork.child_trajectory_ids
    ] == [7, 8]
    assert (
        len(
            {
                service.db.get("trajectories", tid)["metadata"]["executionHash"]
                for tid in fork.child_trajectory_ids
            }
        )
        == 2
    )
    # Reopen the actual on-disk database and inspect persisted canonical/provenance rows.
    from tracelab.storage.database import Database

    reopened = Database(service.data_dir / "tracelab.duckdb")
    try:
        assert reopened.get("trajectories", child["id"])["metadata"] == m
        assert len(reopened.list("tool_resolutions")) == 4
        assert reopened.get("events", result_event["id"])["tool"]["callId"] == "child1"
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "generated,reason",
    [
        ([output(("d", "delete_file", {"path": "a.txt"}))], "unmatched_tool_call"),
        (
            [
                output(
                    ("a", "read_file", {"path": "a.txt"}), ("b", "bash", {"command": "pytest -q"})
                ),
                output(("c", "read_file", {"path": "a.txt"})),
            ],
            "replay_tape_exhausted",
        ),
    ],
)
async def test_policy_termination_is_unscored_complete_fork(service, generated, reason):
    fork, child, events, _ = await run(service, generated)
    assert fork.status == "complete" and child["status"] == "unknown"
    assert child["metadata"]["executionStatus"] == "policy_terminated"
    assert child["metadata"]["terminationReason"] == reason
    assert events[-1]["type"] == "tool_call"


async def test_multiple_calls_partial_resolution_order(service):
    _, child, events, _ = await run(
        service,
        [
            output(("a", "read_file", {"path": "a.txt"}), ("b", "bash", {"command": "wrong"})),
            output(text="must not happen"),
        ],
    )
    assert [e["type"] for e in events[-3:]] == ["tool_call", "tool_result", "tool_call"]
    assert child["metadata"]["modelSteps"] == 1
    assert child["metadata"]["toolCalls"] == 2
    assert child["metadata"]["replayedToolCalls"] == 1


async def test_stub_permanently_disables_replay(service):
    spec = {
        **SPEC,
        "unmatchedToolPolicy": "stub",
        "toolStubs": [
            ToolStub(
                id="s",
                tool_name="write_file",
                arguments={"path": "a.txt", "content": "x"},
                result="Applied",
            ).wire()
        ],
    }
    _, child, events, _ = await run(
        service,
        [
            output(("a", "read_file", {"path": "a.txt"})),
            output(("s", "write_file", {"content": "x", "path": "a.txt"})),
            output(("b", "bash", {"command": "pytest -q"})),
        ],
        spec,
    )
    assert child["metadata"]["replayState"] == "diverged_by_stub"
    assert child["metadata"]["replayedToolCalls"] == child["metadata"]["stubbedToolCalls"] == 1
    assert child["metadata"]["terminationReason"] == "unmatched_tool_call"
    stub = next(e for e in events if e["metadata"].get("toolResultOrigin") == "stub")
    assert stub["metadata"]["synthetic"]
    assert "matchedSourceCallEventId" not in stub["metadata"]


@pytest.mark.parametrize(
    "bounds,reason,steps,tools",
    [
        ({"maxModelSteps": 1}, "max_model_steps", 1, 1),
        ({"maxToolCalls": 1}, "max_tool_calls", 2, 2),
    ],
)
async def test_bounds(service, bounds, reason, steps, tools):
    _, child, _, _ = await run(
        service,
        [
            output(("a", "read_file", {"path": "a.txt"})),
            output(("b", "bash", {"command": "pytest -q"})),
            output(),
        ],
        {**SPEC, **bounds},
    )
    assert child["metadata"]["terminationReason"] == reason
    assert child["metadata"]["executionStatus"] == "bounded"
    assert (child["metadata"]["modelSteps"], child["metadata"]["toolCalls"]) == (steps, tools)


@pytest.mark.parametrize("failure", [RuntimeError("provider crashed"), asyncio.CancelledError()])
async def test_errors_and_cancellation_keep_partial_history(service, failure):
    fork, _, _, _ = await setup(service, [output(("a", "read_file", {"path": "a.txt"})), failure])
    with pytest.raises(type(failure)):
        await service.forks.run(Job(kind="fork", name="test"), fork)
    child = service.db.get("trajectories", fork.child_trajectory_ids[0])
    assert child["status"] == (
        "cancelled" if isinstance(failure, asyncio.CancelledError) else "error"
    )
    assert child["metadata"]["terminationReason"] == (
        "cancelled" if isinstance(failure, asyncio.CancelledError) else "model_error"
    )
    assert len(service.db.list("tool_resolutions")) == 1
    assert child["eventCount"] == 4


async def test_preview_purity_hashes_and_source_immutability(service):
    fork, events, records, _ = await setup(service)
    before = {
        t: copy.deepcopy(service.db.list(t))
        for t in ("forks", "trajectories", "events", "source_records", "tool_resolutions")
    }
    p = await service.dispatch("forks.preview", fork.wire())
    assert p["replaySupport"]["supported"]
    assert p["toolCatalog"]["count"] == 2 and p["replayPlan"]["entryCount"] == 2
    assert "alpha" not in json.dumps(p["replayPlan"])
    prepared = await service.forks.prepare(fork)
    assert prepared.execution_hash == p["executionHash"]
    assert {t: service.db.list(t) for t in before} == before
    fork.execution_spec.max_model_steps += 1
    p2 = await service.forks.prepare(fork)
    assert p2.input_hash == p["inputHash"] and p2.execution_hash != p["executionHash"]
    assert p2.replay_plan_hash == p["replayPlan"]["hash"]


@pytest.mark.parametrize(
    "kind,code",
    [
        ("missing", "tool_schema_unavailable"),
        ("dynamic", "dynamic_tool_catalog_unsupported"),
        ("unpaired", "ambiguous_tool_result"),
        ("multimodal", "unsupported_tool_result"),
    ],
)
async def test_fail_closed_support(service, kind, code):
    fork, events, records, _ = await setup(service)
    if kind in ("missing", "dynamic"):
        record = records[0] if kind == "missing" else records[2]
        record["raw"]["tools"] = None if kind == "missing" else SCHEMAS[:1]
        service.db.put("source_records", record)
    else:
        event = next(e for e in events if e.type == "tool_result")
        if kind == "unpaired":
            event.tool.call_id = "orphan"
        else:
            event.tool.result = [{"type": "image", "image": "data:..."}]
        service.db.put("events", event)
    preview = await service.dispatch("forks.preview", fork.wire())
    assert preview["replaySupport"]["reasonCode"] == code
    with pytest.raises(ReplayUnsupported):
        await service.forks.run(Job(kind="fork", name="test"), fork)
    assert not fork.child_trajectory_ids


async def test_real_inspect_multistep_one_native_log(service, monkeypatch):
    from inspect_ai._util import appdirs
    from inspect_ai.log import read_eval_log
    from inspect_ai.model import ModelOutput, get_model
    from tracelab.inspect_adapter import replay

    monkeypatch.setattr(appdirs, "user_data_path", lambda _: service.data_dir / "inspect-state")
    monkeypatch.setenv("INSPECT_TRACE_FILE", str(service.data_dir / "trace.log"))
    outputs = [
        output(("c1", "read_file", {"path": "a.txt"})),
        output(("c2", "bash", {"command": "pytest -q"})),
        output(text="Done."),
    ]
    model = get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.model_validate(o) for o in outputs],
        memoize=False,
    )
    monkeypatch.setattr(replay, "get_model", lambda *a, **kw: model)
    fork, _, _, _ = await setup(service)
    await service.forks.run(Job(kind="fork", name="real Inspect, mock model"), fork)
    child = service.db.get("trajectories", fork.child_trajectory_ids[0])
    log = read_eval_log(child["metadata"]["logPath"])
    assert log.status == "success"
    assert log.samples[0].output.completion == "Done."
    assert len([e for e in log.samples[0].events if e.event == "model"]) == 3
    assert [m.tool_call_id for m in log.samples[0].messages if m.role == "tool"] == ["c1", "c2"]
    assert not [e for e in log.samples[0].events if e.event in ("tool", "sandbox")]
    assert child["metadata"]["modelSteps"] == 3
    assert len(list((service.data_dir / "fork-logs").rglob("*.eval"))) == 1
    assert child["status"] == "unknown" and child["scores"] == {}


def test_stub_matching_is_exact_duplicate_stubs_rejected():
    stub = {"id": "a", "toolName": "bash", "arguments": {"command": "pytest -q"}, "result": "ok"}
    spec = ForkExecutionSpec.model_validate(
        {**SPEC, "unmatchedToolPolicy": "stub", "toolStubs": [stub]}
    )
    r = ReplayResolver((), spec)
    with pytest.raises(ReplayUnsupported):
        r.resolve("bash", {"command": " pytest -q "})
    assert not r.diverged_by_stub
    assert r.resolve("bash", {"command": "pytest -q"})[0] == "stub"
    spec.tool_stubs.append(ToolStub.model_validate({**stub, "id": "b"}))
    with pytest.raises(ValueError, match="ambiguous"):
        ReplayResolver((), spec)


async def test_recorded_error_and_unknown_usage(service):
    fork, events, _, seen = await setup(
        service, [output(("c", "read_file", {"path": "a.txt"}), usage=False), output()]
    )
    result = next(e for e in events if e.type == "tool_result")
    result.tool.result = None
    result.tool.error = "denied"
    result.metadata["toolError"] = {"type": "permission", "message": "denied"}
    service.db.put("events", result)
    await service.forks.run(Job(kind="fork", name="errors"), fork)
    assert seen[0][0]["error"] == {"type": "permission", "message": "denied"}
    child = service.db.get("trajectories", fork.child_trajectory_ids[0])
    assert child["totalTokens"] is None and child["inputTokens"] is None
    results = [e for e in await service.load_events(child["id"]) if e["type"] == "tool_result"]
    assert results[0]["tool"]["error"]


async def test_opaque_generated_reasoning_remains_protected(service):
    generated = output(text="ciphertext")
    generated["choices"][0]["message"]["content"] = [
        {"type": "reasoning", "reasoning": "ciphertext", "redacted": True}
    ]
    _, child, events, _ = await run(service, [generated])
    event = events[-1]
    detail = await service.dispatch("events.get", {"id": event["id"]})
    assert detail["event"]["content"] is None
    assert detail["event"]["metadata"]["presentationClass"] == "opaque"
    assert "ciphertext" not in json.dumps(detail)
    assert "ciphertext" in json.dumps(await service.dispatch("events.raw", {"id": event["id"]}))
    from tracelab.analysis.semantic import semantic_events

    assert "ciphertext" not in semantic_events([event])[0].summary


async def test_source_point_not_intervention_target_defines_tape(service):
    fork, events, _, _ = await setup(service)
    source = next(e for e in events if e.type == "tool_result")
    fork.source_event_id = source.id
    fork.interventions = Fork.model_validate(
        {
            **fork.wire(),
            "interventions": [
                {"type": "replace_content", "eventId": "t:e0", "content": "Edited earlier task"}
            ],
        }
    ).interventions
    p = await service.forks.prepare(fork)
    assert p.replay_tape[0].tool_name == "bash" and len(p.replay_tape) == 1
    assert p.messages[0]["content"] == "Edited earlier task"


async def test_result_changes_plan_and_execution_not_context_hash(service):
    fork, events, _, _ = await setup(service)
    before = await service.forks.prepare(fork)
    result = next(e for e in events if e.type == "tool_result")
    result.tool.result = "a different recorded observation"
    service.db.put("events", result)
    after = await service.forks.prepare(fork)
    assert before.input_hash == after.input_hash
    assert before.replay_plan_hash != after.replay_plan_hash
    assert before.execution_hash != after.execution_hash


async def test_no_future_calls_and_unreconstructable_prefix(service):
    fork, events, _, _ = await setup(service)
    # A call with no result in the prefix is not repaired by the future replay tape.
    fork.source_event_id = next(e.id for e in events if e.type == "tool_call")
    assert (await service.forks.prepare(fork)).replay_support[
        "reasonCode"
    ] == "context_reconstruction_unavailable"
    fork.source_event_id = next(e.id for e in reversed(events) if e.type == "tool_result")
    assert (await service.forks.prepare(fork)).replay_support[
        "reasonCode"
    ] == "no_future_tool_calls"


async def test_multiple_stubs_remain_synthetic_and_duplicate_call_ids_error(service):
    stubs = [
        {"id": name, "toolName": name, "arguments": {}, "result": "synthetic"}
        for name in ("a", "b")
    ]
    _, child, _, _ = await run(
        service,
        [output(("1", "a", {}), ("2", "b", {})), output()],
        {**SPEC, "unmatchedToolPolicy": "stub", "toolStubs": stubs},
    )
    assert (
        child["metadata"]["stubbedToolCalls"] == 2 and child["metadata"]["replayedToolCalls"] == 0
    )
    fork, _, _, _ = await setup(
        service,
        [output(("x", "read_file", {"path": "a.txt"}), ("x", "bash", {"command": "pytest -q"}))],
    )
    with pytest.raises(RuntimeError):
        await service.forks.run(Job(kind="fork", name="invalid ids"), fork)
    child = service.db.get("trajectories", fork.child_trajectory_ids[0])
    assert child["metadata"]["terminationReason"] == "tool_resolution_error"


async def test_real_inspect_cancellation_preserves_results_and_stops_calls(service, monkeypatch):
    from inspect_ai._util import appdirs
    from inspect_ai.model import ModelOutput, get_model
    from tracelab.inspect_adapter import replay

    monkeypatch.setattr(appdirs, "user_data_path", lambda _: service.data_dir / "inspect-state")
    monkeypatch.setenv("INSPECT_TRACE_FILE", str(service.data_dir / "trace.log"))
    model = get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.model_validate(output(("c", "read_file", {"path": "a.txt"})))],
        memoize=False,
    )
    original = model.generate
    calls, waiting = 0, asyncio.Event()

    async def generate(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            waiting.set()
            await asyncio.sleep(30)
        return await original(*args, **kwargs)

    monkeypatch.setattr(model, "generate", generate)
    monkeypatch.setattr(replay, "get_model", lambda *a, **kw: model)
    fork, _, _, _ = await setup(service)
    task = asyncio.create_task(service.forks.run(Job(kind="fork", name="cancel"), fork))
    await asyncio.wait_for(waiting.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    child = service.db.get("trajectories", fork.child_trajectory_ids[0])
    assert child["status"] == "cancelled"
    assert child["metadata"]["terminationReason"] == "cancelled"
    assert len(service.db.list("tool_resolutions")) == 1
    assert calls == 2


async def test_generated_shell_call_never_executes(service, monkeypatch, tmp_path):
    from inspect_ai._util import appdirs
    from inspect_ai.model import ModelOutput, get_model
    from tracelab.inspect_adapter import replay

    monkeypatch.setattr(appdirs, "user_data_path", lambda _: service.data_dir / "inspect-state")
    monkeypatch.setenv("INSPECT_TRACE_FILE", str(service.data_dir / "trace.log"))
    sentinel = tmp_path / "must-not-be-created"
    generated = output(("host-danger", "bash", {"command": f"touch {sentinel}"}))
    model = get_model(
        "mockllm/model", custom_outputs=[ModelOutput.model_validate(generated)], memoize=False
    )
    monkeypatch.setattr(replay, "get_model", lambda *a, **kw: model)
    fork, _, _, _ = await setup(service)
    await service.forks.run(Job(kind="fork", name="no execution"), fork)
    assert not sentinel.exists()
    child = service.db.get("trajectories", fork.child_trajectory_ids[0])
    assert child["metadata"]["terminationReason"] == "unmatched_tool_call"
    assert child["status"] == "unknown" and fork.status == "complete"


async def test_run_route_rejects_unavailable_before_creating_experiment_objects(service):
    fork, _, records, _ = await setup(service)
    records[0]["raw"]["tools"] = []
    service.db.put("source_records", records[0])
    with pytest.raises(ValueError, match="tool_schema_unavailable"):
        await service.dispatch("forks.run", fork.wire())
    assert not service.db.list("forks") and not service.db.list("jobs")


async def test_source_rows_immutable_and_resolution_api(service):
    fork, _, _, _ = await setup(service, [output(("a", "read_file", {"path": "a.txt"})), output()])
    before = {t: service.db.list(t, "trajectory_id=?", ["t"]) for t in ("events", "source_records")}
    await service.forks.run(Job(kind="fork", name="immutable"), fork)
    assert {t: service.db.list(t, "trajectory_id=?", ["t"]) for t in before} == before
    assert (
        len(
            await service.dispatch(
                "forks.resolutions", {"trajectoryId": fork.child_trajectory_ids[0]}
            )
        )
        == 1
    )


def test_missing_and_orphan_future_results_fail_closed():
    events, _ = normalize_sample("t", source_sample())
    wire = [e.wire() for e in events]
    missing = [e for e in wire if e["type"] != "tool_result"]
    with pytest.raises(ReplayUnsupported) as exc:
        build_replay_tape(missing, 0)
    assert exc.value.code == "ambiguous_tool_result"
    wire.append(
        {
            **wire[-1],
            "id": "orphan",
            "index": len(wire),
            "type": "tool_result",
            "tool": {"name": "bash", "callId": "orphan", "result": "unpaired"},
        }
    )
    with pytest.raises(ReplayUnsupported) as exc:
        build_replay_tape(wire, 0)
    assert exc.value.code == "ambiguous_tool_result"


def test_catalog_never_silently_drops_schema_constraints():
    from tracelab.inspect_adapter.tool_catalog import recorded_tool_info

    info = recorded_tool_info("a", None, {"type": "object", "properties": {}})
    assert info.parameters.additionalProperties is True
    with pytest.raises(ReplayUnsupported, match="discard"):
        recorded_tool_info(
            "a",
            "",
            {
                "type": "object",
                "properties": {"x": {"type": "string", "unsupported_constraint": True}},
            },
        )


async def test_completed_branch_opens_after_service_restart(tmp_path):
    from tracelab.api.service import Service

    service = Service(tmp_path / "restart")
    try:
        fork, child, events, _ = await run(
            service, [output(("a", "read_file", {"path": "a.txt"})), output()]
        )
        result_id = next(e["id"] for e in events if e["type"] == "tool_result")
    finally:
        await service.close()
    service = Service(tmp_path / "restart")
    try:
        stored_fork = Fork.model_validate(service.db.get("forks", fork.id))
        assert (
            stored_fork.execution_spec.continuation == "multi_step"
            and stored_fork.status == "complete"
        )
        reopened = await service.dispatch("trajectories.get", {"id": child["id"]})
        assert reopened["trajectory"]["metadata"]["terminationReason"] == "assistant_completed"
        assert (await service.dispatch("events.get", {"id": result_id}))["event"]["metadata"][
            "toolResultOrigin"
        ] == "recorded_replay"
        assert len(await service.dispatch("forks.resolutions", {"trajectoryId": child["id"]})) == 1
        assert (await service.dispatch("events.raw", {"id": result_id}))["raw"][
            "type"
        ] == "tracelab_tool_replay"
    finally:
        await service.close()


async def test_rpc_job_uses_prepared_replay_and_schedules_only_cheap_analysis(service):
    fork, _, _, _ = await setup(service, [output(("a", "read_file", {"path": "a.txt"})), output()])
    job = await service.dispatch("forks.run", fork.wire())
    await service.jobs.tasks[job["id"]]
    stored = service.db.get("forks", fork.id)
    assert service.db.get("jobs", job["id"])["status"] == "complete"
    assert stored["status"] == "complete" and len(stored["childTrajectoryIds"]) == 1
    assert stored["metadata"]["executionHash"]
    assert "analysisJobId" in stored["metadata"]
    await asyncio.gather(*list(service.jobs.tasks.values()))
    analysis = service.db.get("jobs", stored["metadata"]["analysisJobId"])
    assert analysis["status"] == "complete"
    assert "LLM detectors are never silently rerun" in analysis["metadata"]["llmPolicy"]


async def test_catalog_follows_copied_ancestor_source_record_ids(service):
    fork, _, records, _ = await setup(service)
    # A branch prefix retains sourceRecordId but its raw record belongs to its ancestor.
    records[0]["trajectoryId"] = "ancestor"
    service.db.put("source_records", records[0])
    prepared = await service.forks.prepare(fork)
    assert prepared.replay_support["supported"]
    assert records[0]["id"] in prepared.tool_catalog.source_record_ids
    # The old catalog cannot be skipped when it differs from later child generations.
    records[0]["raw"]["tools"] = SCHEMAS[:1]
    service.db.put("source_records", records[0])
    prepared = await service.forks.prepare(fork)
    assert prepared.replay_support["reasonCode"] == "dynamic_tool_catalog_unsupported"


async def test_provider_parse_error_never_matches_repaired_arguments(service):
    value = output(("a", "read_file", {"path": "a.txt"}))
    value["choices"][0]["message"]["tool_calls"][0]["parse_error"] = "Invalid provider JSON"
    fork, _, _, _ = await setup(service, [value])
    with pytest.raises(RuntimeError):
        await service.forks.run(Job(kind="fork", name="malformed provider call"), fork)
    child = service.db.get("trajectories", fork.child_trajectory_ids[0])
    assert child["metadata"]["terminationReason"] == "tool_resolution_error"
    assert not service.db.list("tool_resolutions")
    events = await service.load_events(child["id"])
    assert events[-1]["type"] == "tool_call"
    raw = await service.dispatch("events.raw", {"id": events[-1]["id"]})
    assert "Invalid provider JSON" in json.dumps(raw)
