import copy

import pytest
from tracelab.forks.context import apply_interventions, context_messages
from tracelab.models.domain import Fork, Job, Trajectory, Workspace


def test_interventions_are_immutable_and_validate_prefix(event_factory):
    original = [
        event_factory(0, "system", "old system"),
        event_factory(1, "user", "old question"),
    ]
    before = copy.deepcopy(original)
    fork = Fork(
        source_trajectory_id="t",
        source_event_id="t:e1",
        interventions=[
            {"type": "replace_content", "eventId": "t:e1", "content": "new question"},
            {"type": "system_prompt_override", "content": "new system"},
            {"type": "append_message", "role": "user", "content": "one constraint"},
            {"type": "model_override", "model": "new-model"},
            {"type": "generation_override", "parameters": {"temperature": 0.4}},
        ],
    )
    events, appended, config = apply_interventions(original, fork)
    assert original == before
    messages = context_messages(events, appended)
    assert [m["content"] for m in messages] == [
        "new system",
        "new question",
        "one constraint",
    ]
    assert config == {"model": "new-model", "parameters": {"temperature": 0.4}}
    fork.interventions = [
        __import__("tracelab.models.domain", fromlist=["RemoveEvent"]).RemoveEvent(
            type="remove_event", event_id="future"
        )
    ]
    with pytest.raises(ValueError, match="selected prefix"):
        apply_interventions(original, fork)


def test_tool_protocol_rejects_pending_and_orphaned_results(event_factory):
    call = event_factory(
        0,
        "tool_call",
        tool={"name": "bash", "callId": "c", "arguments": {"command": "pwd"}},
    )
    result = event_factory(
        1,
        "tool_result",
        "/work",
        tool={"name": "bash", "callId": "c", "result": "/work"},
    )
    with pytest.raises(ValueError, match="pending tool"):
        context_messages([call], [])
    with pytest.raises(ValueError, match="no matching call"):
        context_messages([result], [])
    assert context_messages([call, result], [])[1]["tool_call_id"] == "c"


def test_tool_errors_and_signed_reasoning_are_preserved(event_factory):
    from tracelab.inspect_adapter.normalize import normalize_sample

    messages = [
        {
            "role": "assistant",
            "content": [{"type": "reasoning", "reasoning": "consider", "signature": "signed"}],
            "tool_calls": [{"id": "c", "function": "bash", "arguments": {}}],
        },
        {
            "role": "tool",
            "tool_call_id": "c",
            "function": "bash",
            "content": "",
            "error": {"type": "timeout", "message": "Timed out"},
        },
    ]
    events, _ = normalize_sample("t", {"messages": messages})
    context = context_messages([e.wire() for e in events], [])
    assert context[0]["content"][0]["signature"] == "signed"
    assert context[-1]["error"] == {"type": "timeout", "message": "Timed out"}
    fork = Fork(
        source_trajectory_id="t",
        source_event_id=events[-1].id,
        interventions=[
            {"type": "replace_content", "eventId": events[0].id, "content": "Changed reasoning"}
        ],
    )
    with pytest.raises(ValueError, match="Signed reasoning"):
        apply_interventions([e.wire() for e in events], fork)


def test_unsupported_context_is_not_silently_replaced_by_a_placeholder(event_factory):
    image = event_factory(
        metadata={"contentBlock": {"type": "image", "image": "data:image/png;base64,example"}}
    )
    with pytest.raises(ValueError, match="unsupported non-text"):
        context_messages([image], [])
    compacted = event_factory(type="other", metadata={"inspectType": "compaction"})
    with pytest.raises(ValueError, match="compaction"):
        context_messages([compacted], [])


async def test_actual_inspect_continuation_writes_native_log(service, monkeypatch, event_factory):
    from inspect_ai._util import appdirs
    from inspect_ai.log import read_eval_log
    from inspect_ai.model import ModelOutput, ModelUsage, get_model
    from tracelab.inspect_adapter import replay

    service.data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        appdirs, "user_data_path", lambda _: service.data_dir / "inspect-test-state"
    )
    monkeypatch.setenv("INSPECT_TRACE_FILE", str(service.data_dir / "inspect-trace.log"))
    # Public Inspect test model; execution and native log writing are real, with no API calls.
    generated = ModelOutput.from_content(
        "mockllm/model", "The changed context leads to this continuation."
    )
    generated.usage = ModelUsage(input_tokens=17, output_tokens=9, total_tokens=26)
    monkeypatch.setattr(
        replay,
        "get_model",
        lambda *a, **kw: get_model("mockllm/model", custom_outputs=[generated], memoize=False),
    )
    workspace = Workspace(name="fork test")
    service.db.put("workspaces", workspace)
    service.db.put("experiments", {"id": "exp", "workspaceId": workspace.id, "name": "source"})
    parent = Trajectory(
        id="t",
        experiment_id="exp",
        sample_id="7",
        loaded=True,
        event_count=2,
        model="mock-model",
        status="success",
        scores={"task": 1},
    )
    service.db.put("trajectories", parent)
    events = [
        event_factory(0, "system", "Be concise"),
        event_factory(1, "user", "Original question"),
    ]
    service.db.put_many("events", events)
    fork = Fork(
        source_trajectory_id="t",
        source_event_id="t:e1",
        replication_count=2,
        interventions=[
            {
                "type": "replace_content",
                "eventId": "t:e1",
                "content": "Intervened question",
            }
        ],
        model_overrides={
            "model": "mock-model",
            "provider": "local",
            "parameters": {"seed": 42},
        },
    )
    job = Job(kind="fork", name="fork")
    await service.forks.run(job, fork)
    assert fork.status == "complete"
    assert len(fork.child_trajectory_ids) == 2
    for index, tid in enumerate(fork.child_trajectory_ids):
        child = service.db.get("trajectories", tid)
        assert child["parentTrajectoryId"] == "t"
        assert child["status"] == "unknown"
        assert child["scores"] == {}
        assert child["metadata"]["parameters"]["seed"] == 42 + index
        log = read_eval_log(child["metadata"]["logPath"])
        assert log.status == "success"
        assert log.samples[0].output.completion.startswith("The changed context")
        child_events = await service.load_events(tid)
        assert [e["content"] for e in child_events] == [
            "Be concise",
            "Intervened question",
            "The changed context leads to this continuation.",
        ]
    assert service.db.get("events", "t:e1")["content"] == "Original question"
    assert service.db.get("trajectories", "t")["scores"] == {"task": 1}


async def test_checkpoint_rejected_before_any_execution(service):
    with pytest.raises(ValueError, match="Checkpoint restoration is unavailable"):
        await service.dispatch(
            "forks.run",
            {
                "sourceTrajectoryId": "t",
                "sourceEventId": "t:e1",
                "fidelity": "checkpoint_restored",
            },
        )


async def test_failed_fork_keeps_parent_and_exposes_error(service, event_factory):
    parent = Trajectory(id="t", experiment_id="e", sample_id="1", loaded=True, event_count=1)
    service.db.put("trajectories", parent)
    service.db.put("events", event_factory())
    job = await service.dispatch(
        "forks.run",
        {
            "sourceTrajectoryId": "t",
            "sourceEventId": "t:e0",
            "modelOverrides": {"model": "x", "provider": "missing"},
        },
    )
    await service.jobs.tasks[job["id"]]
    assert service.db.get("jobs", job["id"])["status"] == "failed"
    assert service.db.list("forks")[0]["status"] == "failed"
    assert service.db.get("events", "t:e0")
