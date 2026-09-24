"""Presentation never substitutes interpretation for preservation."""

import copy
import json

import pytest
from tracelab.analysis.interpretation import interpret
from tracelab.analysis.outline import build_outline
from tracelab.analysis.semantic import coordinates, semantic_events
from tracelab.classifiers.runner import ClassifierRunner, classifier_input
from tracelab.inspect_adapter.normalize import normalize_sample
from tracelab.models.domain import ClassifierDefinition, Job, ProviderSettings, Trajectory
from tracelab.presentation import classify, prepare_event, research_events, visible_event
from tracelab.presentation.storage import counts, prepared_events
from tracelab.segmentation.service import run_segmentation
from tracelab.storage.queries import event_location, event_page, search

PAYLOAD = "EmgKZgEMOdbHJdbGKO7AzNj+hbp7+u00cQqtTEST"


def opaque(factory, index=70, **block):
    return factory(
        index,
        type="reasoning",
        content=PAYLOAD,
        metadata={
            "contentBlock": {"type": "reasoning", "reasoning": PAYLOAD, "redacted": True, **block}
        },
    )


@pytest.mark.parametrize(
    "native", ["span_begin", "span_end", "sample_init", "sandbox", "state", "store"]
)
def test_known_inspect_runtime(native):
    sample = {"events": [{"event": native}]}
    events, sources = normalize_sample("t", sample)
    assert len(events) == 1
    assert events[0].metadata["presentationClass"] == "runtime"
    assert events[0].metadata["inspectType"] == native
    assert sources[0]["raw"] == sample["events"][0]


@pytest.mark.parametrize(
    "action,detail", [("exec", {"cmd": ["pytest"]}), ("write_file", {"file": "src/a.py"})]
)
def test_sandbox_actions_are_preserved_as_meaningful_environment(action, detail):
    raw = {"event": "sandbox", "action": action, **detail}
    events, sources = normalize_sample("t", {"events": [raw]})
    assert events[0].metadata["presentationClass"] == "semantic"
    assert events[0].metadata["environmentEffects"][0]["action"] == action
    assert sources[0]["raw"] == raw


@pytest.mark.parametrize(
    "kind",
    [
        "system",
        "user",
        "assistant",
        "reasoning",
        "tool_call",
        "tool_result",
        "environment",
        "error",
        "score",
        "checkpoint",
    ],
)
def test_research_types(event_factory, kind):
    assert classify(event_factory(type=kind)) == "semantic"
    assert classify(event_factory(type="other", content="unrecognized native record")) == "runtime"


def test_visibility_is_explicit_not_a_base64_guess(event_factory):
    original = opaque(event_factory)
    before = copy.deepcopy(original)
    view = visible_event(original)
    assert original == before
    assert view["content"] is None
    assert view["metadata"]["presentationClass"] == "opaque"
    assert view["metadata"]["reasoningVisibility"] == "redacted"
    assert PAYLOAD not in json.dumps(view)
    assert prepare_event(original)["metadata"]["contentBlock"]["reasoning"] == PAYLOAD
    assert (
        visible_event(opaque(event_factory, summary="Readable summary"))["content"]
        == "Readable summary"
    )
    signed = opaque(
        event_factory, redacted=False, signature="signed-state", reasoning="Readable reasoning"
    )
    assert visible_event(signed)["content"] == "Readable reasoning"
    assert classify(signed) == "semantic"
    assert visible_event(opaque(event_factory, redacted=False))["content"] == PAYLOAD
    encrypted = opaque(event_factory, redacted=False, encrypted=True)
    assert visible_event(encrypted)["metadata"]["reasoningVisibility"] == "encrypted"
    signature = opaque(event_factory, redacted=False, reasoning="", signature="signed-state")
    assert visible_event(signature)["metadata"]["reasoningVisibility"] == "opaque"


def test_normalization_preserves_raw_and_groups_only_recorded_model_output():
    sample = {
        "events": [
            {"event": "sample_init"},
            {
                "event": "model",
                "input": [{"role": "user", "content": "Task"}],
                "output": {
                    "usage": {"output_tokens": 9},
                    "choices": [
                        {
                            "message": {
                                "id": "generation",
                                "role": "assistant",
                                "content": [
                                    {"type": "reasoning", "reasoning": PAYLOAD, "redacted": True},
                                    {"type": "text", "text": "Tool plan"},
                                ],
                                "tool_calls": [
                                    {"id": "c", "function": "bash", "arguments": {"cmd": "ls"}}
                                ],
                            }
                        }
                    ],
                },
            },
        ]
    }
    original = copy.deepcopy(sample)
    events, sources = normalize_sample("t", sample)
    assert sample == original
    assert sources[1]["raw"] == sample["events"][1]
    wire = [e.wire() for e in events]
    reason = next(e for e in wire if e["type"] == "reasoning")
    assert reason["content"] is None
    assert reason["metadata"]["contentBlock"]["reasoning"] == PAYLOAD
    calls = [e["metadata"].get("modelCallId") for e in wire]
    assert calls == [None, None, "t:raw1:output:0", "t:raw1:output:0", "t:raw1:output:0"]
    assert sum(p["modelCallBoundary"] for p in coordinates(semantic_events(wire))["points"]) == 1
    assert PAYLOAD not in json.dumps(classifier_input(wire))
    assert PAYLOAD not in json.dumps([e.wire() for e in semantic_events(wire)])


def seed(service, factory):
    service.db.put("experiments", {"id": "exp", "workspaceId": "ws"})
    service.db.put(
        "trajectories",
        Trajectory(id="t", experiment_id="exp", sample_id="s", loaded=True, event_count=101),
    )
    events = [
        factory(i, type="reasoning" if i % 6 == 4 else "assistant", content=f"readable {i}")
        for i in range(101)
    ]
    events[0] = factory(
        0, type="other", content="span_begin", metadata={"inspectType": "span_begin"}
    )
    events[70] = opaque(factory)
    events[80] = factory(80, type="tool_result", tool={"name": "bash", "error": "failure"})
    events[90] = factory(
        90,
        type="environment",
        content="sandbox",
        metadata={"inspectType": "sandbox", "sourceRecordId": "s90"},
    )
    service.db.put(
        "source_records",
        {
            "id": "s90",
            "trajectoryId": "t",
            "raw": {"event": "sandbox", "action": "exec", "cmd": ["ls"]},
        },
    )
    service.db.put_many("events", events)
    return events


def test_legacy_projection_counts_locate_and_raw_immutability(service, event_factory):
    originals = seed(service, event_factory)
    assert counts(service.db, "t") == {
        "recorded": 101,
        "research": 100,
        "semantic": 99,
        "runtime": 1,
        "opaque": 1,
    }
    reasoning = event_location(service.db, "t", 70, mode="reasoning")
    assert reasoning == {"offset": 11, "exact": True, "eventIndex": 70, "nearestEventIndex": None}
    assert event_location(service.db, "t", 70)["offset"] == 69
    assert (
        event_page(service.db, "t", mode="reasoning", offset=11, limit=1)["items"][0]["index"] == 70
    )
    assert event_page(service.db, "t", offset=69, limit=1)["items"][0]["index"] == 70
    assert event_page(service.db, "t", mode="runtime")["items"][0]["index"] == 0
    assert service.db.list("events", order="event_index") == originals
    assert prepared_events(service.db, "t")[90]["content"] == "exec: ['ls']"
    assert search(service.db, "ws", PAYLOAD)["total"] == 0
    assert search(service.db, "ws", "span_begin")["total"] == 0
    assert event_page(service.db, "t", query=PAYLOAD)["total"] == 0


@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"mode": "reasoning"},
        {"mode": "tools"},
        {"mode": "errors"},
        {"mode": "runtime"},
        {"mode": "recorded"},
        {"mode": "reasoning", "start": 40, "end": 75},
        {"query": "readable", "start": 50, "end": 78},
        {"query": "nonexistent"},
    ],
)
def test_locate_and_page_share_exact_filter_semantics(service, event_factory, filters):
    seed(service, event_factory)
    rows = event_page(service.db, "t", limit=500, **filters)["items"]
    for requested in [0, 70, 71, 73, 75, 100]:
        location = event_location(service.db, "t", requested, **filters)
        if not rows:
            assert location["offset"] is None and not location["exact"]
            continue
        nearest = min(rows, key=lambda e: (abs(e["index"] - requested), e["index"]))
        assert rows[location["offset"]]["index"] == nearest["index"]
        assert location["exact"] == (requested == nearest["index"])
        assert (
            event_page(service.db, "t", offset=location["offset"], limit=1, **filters)["items"][0]
            == nearest
        )


def test_projection_invalidated_by_canonical_writes(service, event_factory):
    seed(service, event_factory)
    assert event_location(service.db, "t", 70)["offset"] == 69
    service.db.put("events", event_factory(0, type="user"))
    assert event_location(service.db, "t", 70)["offset"] == 70


async def test_event_detail_safe_raw_explicit_and_analysis_safe(service, event_factory):
    originals = seed(service, event_factory)
    detail = await service.dispatch("events.get", {"trajectoryId": "t", "index": 70})
    assert PAYLOAD not in json.dumps(detail)
    assert detail["event"]["metadata"]["reasoningVisibility"] == "redacted"
    raw = await service.dispatch("events.raw", {"id": "t:e70"})
    assert raw == originals[70]
    semantic = semantic_events(await service.load_events("t"))
    assert semantic[0].summary == ""
    assert semantic[70].summary == "[redacted reasoning unavailable]"
    assert PAYLOAD not in json.dumps([e.wire() for e in semantic])
    outline = build_outline("t", semantic)
    assert all("t:e0" not in n.evidence_event_ids for n in outline)
    assert all(n.stats["eventBasis"] == "research" for n in outline)
    located = await service.dispatch(
        "events.locate", {"trajectoryId": "t", "eventIndex": 70, "mode": "reasoning"}
    )
    assert located["offset"] == 11
    assert len(research_events(originals)) == 99  # A placeholder alone establishes no effect.
    assert len(research_events(await service.load_events("t"))) == 100


async def test_actual_classifier_outline_segmentation_prompts_exclude_opaque_and_runtime(
    service, event_factory
):
    seed(service, event_factory)
    prompts = []

    class Provider:
        async def generate_structured(self, **kwargs):
            prompts.append(kwargs["prompt"])
            props = kwargs["schema"]["properties"]
            if "nodes" in props:
                output = {"nodes": []}
            elif "segments" in props:
                output = {
                    "segments": [
                        {
                            "start_event": 0,
                            "end_event": 100,
                            "parent_phase": None,
                            "label": "Recorded activity",
                            "summary": "Test",
                            "confidence": 0.5,
                        }
                    ]
                }
            else:
                output = {"score": 0.5, "rationale": "Test double", "evidence_event_ids": ["t:e70"]}
            return {"output": output}

    settings = ProviderSettings(
        id="p",
        name="Test",
        kind="openai_compatible",
        base_url="http://localhost:1/v1",
        api_key_env="UNUSED",
    )
    service.provider_factory = lambda _: (Provider(), settings)
    runner = ClassifierRunner(
        service.db, service.jobs, service.load_events, service.provider_factory
    )
    await runner.run(
        Job(kind="classifier", name="Test"),
        ClassifierDefinition(
            name="Test", prompt="Test", provider="p", model="double", scope="trajectory"
        ),
        ["t"],
    )
    await interpret(service, Job(kind="analysis", name="Test"), "t", "p", "double")
    await run_segmentation(service, Job(kind="segmentation", name="Test"), "t", "p", "double")
    assert len(prompts) == 3
    for prompt in prompts:
        assert PAYLOAD not in prompt
        assert "span_begin" not in prompt
        assert "redacted" in prompt
    provenance = service.db.list("classifier_results")[0]["provenance"]
    assert "t:e0" not in provenance["inputEventIds"]
    assert "t:e70" in provenance["inputEventIds"]


def test_intervened_reasoning_uses_branch_text_and_retains_original_replay(event_factory):
    from tracelab.forks.context import context_messages

    original = opaque(event_factory)
    prepared = prepare_event(original)
    # Opaque model state remains available to the existing replay implementation.
    assert context_messages([prepared], [])[0]["content"][0]["reasoning"] == PAYLOAD
    edited = copy.deepcopy(prepared)
    edited["content"] = "Researcher-supplied replacement"
    edited["metadata"]["intervened"] = True
    assert visible_event(edited)["content"] == "Researcher-supplied replacement"
    assert visible_event(edited)["metadata"]["reasoningVisibility"] == "plaintext"
    assert (
        context_messages([edited], [])[0]["content"][0]["reasoning"]
        == "Researcher-supplied replacement"
    )
    assert edited["metadata"]["contentBlock"]["reasoning"] == PAYLOAD


def test_explicit_source_redaction_takes_precedence_over_stale_visibility(event_factory):
    event = opaque(event_factory)
    event["metadata"]["reasoningVisibility"] = "plaintext"
    assert visible_event(event)["metadata"]["presentationClass"] == "opaque"
    assert visible_event(event)["metadata"]["reasoningVisibility"] == "redacted"


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/output/choices/0", "runtime"),
        ("/messages/1", "runtime"),
        ("/unknown", "runtime"),
        ("/tools/0", "semantic"),
        ("/tool_choice", "semantic"),
    ],
)
def test_task_state_bookkeeping_is_not_new_behavior(path, expected):
    events, sources = normalize_sample(
        "t",
        {
            "events": [
                {"event": "state", "changes": [{"op": "add", "path": path, "value": PAYLOAD}]}
            ]
        },
    )
    assert events[0].metadata["presentationClass"] == expected
    assert PAYLOAD in json.dumps(sources)
    assert PAYLOAD not in json.dumps(classifier_input([events[0].wire()]))


@pytest.mark.parametrize("source_kind,expected", [("model", "source:output:0"), ("unknown", None)])
def test_legacy_call_id_requires_recorded_model_source(
    service, event_factory, source_kind, expected
):
    service.db.put("source_records", {"id": "source", "raw": {"event": source_kind}})
    meta = {"sourceRecordId": "source", "messageKey": "m"}
    service.db.put_many(
        "events",
        [
            event_factory(0, type="reasoning", metadata=meta, tokenUsage={"output": 1}),
            event_factory(1, type="assistant", metadata=meta),
        ],
    )
    assert [e["metadata"].get("modelCallId") for e in prepared_events(service.db, "t")] == [
        expected,
        expected,
    ]
