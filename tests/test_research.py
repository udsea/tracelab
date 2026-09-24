import copy
import json

import duckdb
import pytest
from tracelab.analysis.models import AnalysisSignal, ArtifactRef, ModelInternalSource
from tracelab.analysis.outline import build_outline
from tracelab.analysis.relationships import relationships
from tracelab.analysis.rules import rule_matches
from tracelab.analysis.semantic import coordinates, semantic_events
from tracelab.analysis.statistical import statistical_matches
from tracelab.models.domain import (
    ClassifierDefinition,
    ClassifierOutput,
    ClassifierResult,
    Job,
    Trajectory,
)


def seed(service, events, tid="t"):
    service.db.put("experiments", {"id": "exp", "workspaceId": "ws"})
    service.db.put(
        "trajectories",
        Trajectory(
            id=tid, experiment_id="exp", sample_id="sample", loaded=True, event_count=len(events)
        ),
    )
    service.db.put_many("events", events)


def test_semantic_preserves_source_and_unknown_time(event_factory):
    events = [
        event_factory(
            0,
            "tool_result",
            tool={"name": "bash", "result": {"exit_code": 1, "stdout": "x" * 5000}},
            timestamp="2026-09-01T00:00:00Z",
            metadata={"agentId": "coder", "durationMs": 19400},
        ),
        event_factory(1, "reasoning", timestamp="not-a-time"),
        event_factory(2, "assistant", timestamp="2026-09-01T00:00:02"),
    ]
    original = copy.deepcopy(events)
    sem = semantic_events(events)
    assert sem[0].tool_success is False
    assert len(sem[0].tool_result_summary) < 650
    assert sem[0].duration_ms == 19400 and sem[0].agent_id == "coder"
    coords = coordinates(sem)
    assert coords["missingTimestamps"] == 2
    assert coords["points"][1]["elapsedMs"] is None
    assert events == original


def test_recorded_graph_not_similarity(event_factory):
    events = [
        event_factory(i, "assistant", "same words", metadata={"agentId": a})
        for i, a in enumerate(["planner", "coder", "reviewer"])
    ]
    events[1]["parentEventIds"] = [events[0]["id"]]
    sem = semantic_events(events)
    edges = relationships(sem)
    assert len(edges) == 1 and edges[0]["kind"] == "parent_event"
    outline = build_outline("t", sem)
    assert outline[0].stats["agents"] == ["coder", "planner", "reviewer"]
    assert any(n.kind == "moment" for n in outline)


def test_rules_do_not_call_tests_deception(event_factory):
    events = [
        event_factory(0, "assistant", "I did not modify tests"),
        event_factory(
            1,
            "tool_call",
            tool={"name": "bash", "arguments": {"command": "cat tests/test_auth.py"}},
        ),
    ]
    assert not list(rule_matches(events, {"operation": "claim"}))
    assert not list(rule_matches(events, {"operation": "modification"}))
    assert not list(rule_matches(events, {"operation": "sensitive"}))
    events[1]["metadata"]["sensitive"] = True
    assert list(rule_matches(events, {"operation": "sensitive"}))[0]["evidence"] == ["t:e1"]


def test_change_point_is_grounded_in_distributions(event_factory):
    events = [
        event_factory(
            i, "tool_call", tool={"name": "read_file" if i < 60 else "bash", "arguments": {}}
        )
        for i in range(120)
    ]
    result = list(
        statistical_matches(
            events,
            semantic_events(events),
            {"window": 20, "features": ["tool"], "operators": ["change_point"]},
        )
    )
    assert result
    peak = max(result, key=lambda r: r["score"])
    assert abs(peak["start"] - 60) <= 20
    assert peak["details"]["before"] != peak["details"]["after"]
    assert len(peak["evidence"]) == 40


async def test_signals_projection_versioning_restart(service, event_factory):
    seed(
        service,
        [
            event_factory(
                i, "tool_call", tool={"name": "read_file", "arguments": {"path": "grader.py"}}
            )
            for i in range(6)
        ],
    )
    definition = await service.dispatch(
        "analysis.save",
        {
            "name": "access",
            "detectorType": "rule",
            "parameters": {"operation": "match", "contains": ["grader"]},
        },
    )
    job = await service.dispatch(
        "analysis.run", {"definitionId": definition["id"], "trajectoryIds": ["t"]}
    )
    await service.jobs.tasks[job["id"]]
    assert service.db.get("jobs", job["id"])["status"] == "complete"
    rows = await service.dispatch("analysis.signals", {"trajectoryId": "t"})
    assert len(rows) == 6
    assert rows[0]["provenance"]["inputHash"]
    assert "rawResult" not in rows[0]["provenance"]
    detail = await service.dispatch("analysis.signal", {"trajectoryId": "t", "id": rows[0]["id"]})
    assert detail["signal"]["provenance"]["rawResult"]
    changed = await service.dispatch("analysis.save", {**definition, "name": "edited"})
    assert changed["id"] != definition["id"] and changed["version"] == 2
    assert service.db.get("detector_definitions", definition["id"])["name"] == "access"
    await service.dispatch(
        "annotations.save",
        {"trajectoryId": "t", "startEventIndex": 1, "endEventIndex": 3, "label": "REVIEW"},
    )
    service.db.put(
        "classifier_results",
        ClassifierResult(
            classifier_id="llm",
            run_id="run",
            trajectory_id="t",
            start_event_index=0,
            end_event_index=3,
            output=ClassifierOutput(
                score=0.8,
                evidence_event_ids=["t:e2"],
                counterevidence_event_ids=["t:e1"],
                confidence=0.5,
            ),
            cache_key="k",
        ),
    )
    rows = await service.dispatch("analysis.signals", {"trajectoryId": "t"})
    assert {r["sourceType"] for r in rows} == {"rule", "human", "llm"}
    llm = next(r for r in rows if r["sourceType"] == "llm")
    detail = await service.dispatch("analysis.signal", {"trajectoryId": "t", "id": llm["id"]})
    assert detail["signal"]["metadata"]["output"]["counterevidenceEventIds"] == ["t:e1"]
    overview = await service.dispatch("analysis.overview", {"trajectoryId": "t"})
    assert overview["outline"] and overview["analysisCapabilities"]["tools"]


async def test_white_box_external_parquet_and_mismatched_evidence(service, event_factory, tmp_path):
    seed(service, [event_factory(i) for i in range(3)])
    path = tmp_path / "probe_scores.parquet"
    con = duckdb.connect()
    con.execute(
        "COPY (SELECT 1 AS event_index, 0.69 AS probe_score) TO ? (FORMAT PARQUET)", [str(path)]
    )
    con.close()
    artifact = ArtifactRef(
        trajectory_id="t", uri=str(path), format="parquet", metadata={"measurement": "probe"}
    )
    await service.dispatch("analysis.artifact", artifact.wire())
    source = ModelInternalSource(trajectory_id="t", artifact_ids=[artifact.id], measurement="probe")
    signal = AnalysisSignal(
        trajectory_id="t",
        name="Probe",
        source_type="probe",
        channel="WHITE_BOX",
        start_event_index=1,
        end_event_index=1,
        score=0.69,
        evidence_event_ids=["t:e1"],
        artifact_ref=artifact.id,
    )
    rows = await service.dispatch(
        "analysis.importSignals", {"source": source.wire(), "signals": [signal.wire()]}
    )
    assert rows[0]["score"] == 0.69
    result = await service.dispatch("analysis.signal", {"trajectoryId": "t", "id": signal.id})
    assert result["artifact"]["uri"] == str(path)
    assert path.read_bytes()[:4] == b"PAR1"
    signal.evidence_event_ids = ["other:e0"]
    with pytest.raises(ValueError, match="unavailable"):
        await service.dispatch(
            "analysis.importSignals", {"source": source.wire(), "signals": [signal.wire()]}
        )


async def test_custom_classifier_schema_and_counterevidence(service, event_factory):
    seed(service, [event_factory(0)])

    class Provider:
        async def generate_structured(self, **kwargs):
            return {"output": json.dumps({"custom_statistic": 12})}

    from tracelab.models.domain import ProviderSettings

    service.classifiers.provider_factory = lambda _: (
        Provider(),
        ProviderSettings(
            id="p",
            name="p",
            kind="openai_compatible",
            base_url="http://local",
            api_key_env="",
            default_model="test",
        ),
    )
    definition = ClassifierDefinition(
        name="custom",
        prompt="custom",
        model="test",
        provider="p",
        scope="trajectory",
        return_score=False,
        return_rationale=False,
        return_evidence=False,
        output_schema={
            "type": "object",
            "properties": {"custom_statistic": {"type": "integer"}},
            "required": ["custom_statistic"],
            "additionalProperties": False,
        },
    )
    await service.classifiers.run(Job(kind="classifier", name="custom"), definition, ["t"])
    assert service.db.list("classifier_results")[0]["output"]["custom_statistic"] == 12


async def test_contrastive_missing_signals_and_ambiguous_matching(service, event_factory):
    seed(service, [event_factory(0, tid="a")], "a")
    seed(service, [event_factory(0, tid="b", content="changed")], "b")
    result = await service.dispatch("analysis.compare", {"controlId": "a", "treatmentId": "b"})
    assert result["alignment"]["firstBehaviouralDivergence"] == {"left": 0, "right": 0}
    assert result["signals"] == {}
    pairs = await service.dispatch(
        "analysis.pairs", {"controlIds": ["a"], "treatmentIds": ["b"], "field": "sampleId"}
    )
    assert len(pairs["pairs"]) == 1


def test_missing_token_usage_and_overlapping_novelty(event_factory):
    events = [
        event_factory(i, "tool_call", tool={"name": "bash", "arguments": {"command": "ls"}})
        for i in range(30)
    ]
    for i in range(0, 30, 5):
        events[i]["tokenUsage"] = {"output": 100}
    rows = list(
        statistical_matches(
            events,
            semantic_events(events),
            {"window": 5, "stride": 1, "operators": ["token_spike", "action_novelty"]},
        )
    )
    assert not any(r["label"] == "token_spike" for r in rows)
    assert rows[0]["score"] == 0.2
    assert all(r["score"] == 0 for r in rows[1:])


def test_modification_requires_success_and_claim_requires_test_path(event_factory):
    write = event_factory(
        0, "tool_call", tool={"name": "write_file", "arguments": {"path": "tests/test_auth.py"}}
    )
    result = event_factory(
        1,
        "tool_result",
        tool={"name": "write_file", "result": {"exit_code": 1}},
        parentEventIds=[write["id"]],
    )
    claim = event_factory(2, "assistant", "I did not modify tests")
    events = [write, result, claim]
    assert not list(rule_matches(events, {"operation": "modification"}))
    assert not list(rule_matches(events, {"operation": "claim"}))
    result["tool"]["result"]["exit_code"] = 0
    assert list(rule_matches(events, {"operation": "modification"}))[0]["evidence"] == [
        write["id"],
        result["id"],
    ]
    assert list(rule_matches(events, {"operation": "claim"}))
    write["tool"]["arguments"]["path"] = "grader.py"
    assert not list(rule_matches(events, {"operation": "claim"}))


async def test_overview_cached_and_invalidated_by_segments(service, event_factory):
    seed(service, [event_factory(i) for i in range(6)])
    first = await service.dispatch("analysis.overview", {"trajectoryId": "t"})
    assert first == await service.dispatch("analysis.overview", {"trajectoryId": "t"})
    await service.dispatch(
        "segments.save",
        {
            "trajectoryId": "t",
            "label": "Legacy phase",
            "startEvent": 1,
            "endEvent": 4,
            "summary": "existing",
        },
    )
    second = await service.dispatch("analysis.overview", {"trajectoryId": "t"})
    assert any(n["kind"] == "segment" and n["label"] == "Legacy phase" for n in second["outline"])


async def test_parquet_scalar_import_is_atomic(service, event_factory, tmp_path):
    seed(service, [event_factory(i) for i in range(3)])
    path = tmp_path / "probe_scores.parquet"
    con = duckdb.connect()
    con.execute(
        "COPY (SELECT 1 AS event_index, 0.69::DOUBLE AS score) TO ? (FORMAT PARQUET)", [str(path)]
    )
    con.close()
    result = await service.dispatch(
        "analysis.importParquet",
        {"trajectoryId": "t", "uri": str(path), "measurement": "probe", "name": "Fixture probe"},
    )
    assert result["count"] == 1
    rows = await service.dispatch("analysis.signals", {"trajectoryId": "t"})
    detail = await service.dispatch("analysis.signal", {"trajectoryId": "t", "id": rows[0]["id"]})
    assert detail["signal"]["channel"] == "WHITE_BOX"
    assert detail["signal"]["score"] == 0.69
    assert detail["artifact"]["metadata"]["sha256"]
    before = len(service.db.list("artifacts"))
    con = duckdb.connect()
    con.execute(
        "COPY (SELECT * FROM (VALUES (1, 0.1), (999, 0.2)) t(event_index, score)) TO ? (FORMAT PARQUET)",
        [str(path)],
    )
    con.close()
    with pytest.raises(ValueError):
        await service.dispatch("analysis.importParquet", {"trajectoryId": "t", "uri": str(path)})
    assert len(service.db.list("artifacts")) == before


async def test_rule_zero_matches_distinguished_from_unmeasured(service, event_factory):
    seed(
        service,
        [
            event_factory(
                0,
                "tool_call",
                tid="a",
                tool={"name": "read_file", "arguments": {"path": "grader.py"}},
            )
        ],
        "a",
    )
    seed(service, [event_factory(0, tid="b")], "b")
    definition = await service.dispatch(
        "analysis.save",
        {"name": "Access", "detectorType": "rule", "parameters": {"contains": ["grader"]}},
    )
    for tid in ["a", "b"]:
        job = await service.dispatch(
            "analysis.run", {"definitionId": definition["id"], "trajectoryIds": [tid]}
        )
        await service.jobs.tasks[job["id"]]
        comparison = await service.dispatch(
            "analysis.compare", {"controlId": "a", "treatmentId": "b"}
        )
        if tid == "a":
            assert comparison["ruleMatchCounts"] == {}
            assert comparison["unmatchedSignals"] == [definition["id"]]
    assert comparison["ruleMatchCounts"][definition["id"]] == {
        "control": 1,
        "treatment": 0,
        "delta": -1,
    }


async def test_branch_analysis_is_separate_and_includes_zero_match_rules(service, event_factory):
    from tracelab.analysis.branches import schedule_branch_analysis
    from tracelab.models.domain import Fork

    seed(service, [event_factory(0, tid="a")], "a")
    seed(service, [event_factory(0, tid="b")], "b")
    definition = await service.dispatch(
        "analysis.save",
        {"name": "Access", "detectorType": "rule", "parameters": {"contains": ["grader"]}},
    )
    job = await service.dispatch(
        "analysis.run", {"definitionId": definition["id"], "trajectoryIds": ["a"]}
    )
    await service.jobs.tasks[job["id"]]
    fork = Fork(
        source_trajectory_id="a",
        source_event_id="a:e0",
        child_trajectory_ids=["b"],
        status="complete",
    )
    job = schedule_branch_analysis(service, fork)
    await service.jobs.tasks[job["id"]]
    assert service.db.get("jobs", job["id"])["status"] == "complete"
    comparison = service.db.get("branch_comparisons", f"{fork.id}:b")["comparison"]
    assert comparison["ruleMatchCounts"][definition["id"]]["treatment"] == 0
    assert fork.status == "complete"


def test_explicit_message_envelope_has_no_invented_receiver_event(event_factory):
    events = [
        event_factory(
            0,
            "assistant",
            "Recorded transfer",
            metadata={
                "agentId": "planner",
                "raw": {"recipientAgentId": "coder", "relationshipType": "delegation"},
            },
        )
    ]
    sem = semantic_events(events)
    edges = relationships(sem)
    assert len(edges) == 1
    assert edges[0]["sourceEventId"] == edges[0]["destinationEventId"] == "t:e0"
    assert edges[0]["kind"] == "delegation"
    assert build_outline("t", sem)[0].stats["agents"] == ["coder", "planner"]


def test_span_identifier_is_not_agent_identity(event_factory):
    sem = semantic_events(
        [
            event_factory(
                0,
                "environment",
                metadata={"agentId": "span-123", "structuralKind": "span", "attributes": {}},
            )
        ]
    )
    assert sem[0].agent_id is None


async def test_llm_outline_validates_references_and_caches(service, event_factory):
    from tracelab.analysis.interpretation import interpret
    from tracelab.models.domain import ProviderSettings

    seed(
        service,
        [
            event_factory(
                i,
                "tool_call",
                tool={"name": "bash", "arguments": {"command": "pytest"}},
                metadata={"agentId": "coder"},
            )
            for i in range(3)
        ],
    )
    calls = []

    class Provider:
        async def generate_structured(self, **kwargs):
            calls.append(kwargs)
            node = {
                "kind": "activity",
                "label": "Verification",
                "summary": "Recorded test calls",
                "event_ids": ["foreign"] if len(calls) == 1 else ["t:e0", "t:e2"],
            }
            return {"output": json.dumps({"nodes": [node]})}

    service.provider_factory = lambda _: (
        Provider(),
        ProviderSettings(
            id="p",
            name="p",
            kind="openai_compatible",
            base_url="http://local",
            api_key_env="",
            default_model="mock",
        ),
    )
    await interpret(service, Job(kind="analysis", name="outline"), "t", "p", "mock")
    assert len(calls) == 2
    assert "toolArgumentsSummary" in calls[0]["prompt"] and "coder" in calls[0]["prompt"]
    nodes = service.db.list("outline_nodes")
    assert nodes[0]["kind"] == "activity" and nodes[0]["evidenceEventIds"] == ["t:e0", "t:e2"]
    await interpret(service, Job(kind="analysis", name="outline"), "t", "p", "mock")
    assert len(calls) == 2
