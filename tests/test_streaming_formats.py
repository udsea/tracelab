import asyncio
import json

import pytest
from tracelab.importers.registry import choose
from tracelab.ingestion.bundles import import_bundle
from tracelab.ingestion.universal import import_sources
from tracelab.models.domain import Job
from tracelab.sources.local import LocalSourceProvider
from tracelab.sources.refs import source_ref


def local(path, value):
    path.write_text(json.dumps(value))
    source = LocalSourceProvider()
    return source, source.stat(source_ref(str(path))).ref


def test_otlp_spans_keep_tree_errors_and_messages(tmp_path):
    def attr(key, value):
        return {"key": key, "value": {"stringValue": value}}

    raw = {
        "resourceSpans": [
            {
                "resource": {"attributes": [attr("service.name", "research")]},
                "scopeSpans": [
                    {
                        "scope": {"name": "sdk"},
                        "spans": [
                            {"traceId": "t", "spanId": "workflow", "name": "workflow"},
                            {
                                "traceId": "t",
                                "spanId": "agent",
                                "parentSpanId": "workflow",
                                "name": "planner",
                                "attributes": [attr("gen_ai.operation.name", "invoke_agent")],
                            },
                            {
                                "traceId": "t",
                                "spanId": "llm",
                                "parentSpanId": "agent",
                                "name": "generation",
                                "startTimeUnixNano": "1700000000000000000",
                                "endTimeUnixNano": "1700000001000000000",
                                "attributes": [
                                    attr("gen_ai.operation.name", "chat"),
                                    attr("unknown.attribute", "retained"),
                                    attr(
                                        "gen_ai.output.messages",
                                        '[{"role":"assistant","content":"Answer"}]',
                                    ),
                                ],
                            },
                            {
                                "traceId": "t",
                                "spanId": "tool",
                                "parentSpanId": "agent",
                                "name": "read_file",
                                "attributes": [attr("gen_ai.operation.name", "execute_tool")],
                                "status": {"code": 2, "message": "Missing file"},
                            },
                        ],
                    }
                ],
            }
        ]
    }
    source, ref = local(tmp_path / "otel.json", raw)
    importer, _ = choose(source, ref)
    assert importer.name == "otel"
    events = importer.load_trajectory(source, importer.discover_runs(source, ref)[0]).events
    spans = {e.metadata["spanId"]: e for e in events if e.metadata.get("spanId")}
    assert spans["agent"].parent_event_ids == [spans["workflow"].id]
    assert spans["llm"].parent_event_ids == [spans["agent"].id]
    assert spans["tool"].type == "error" and spans["tool"].tool.error == "Missing file"
    assert spans["llm"].metadata["durationMs"] == 1000
    assert spans["llm"].metadata["attributes"]["unknown.attribute"] == "retained"
    assert spans["llm"].metadata["scope"] == {"name": "sdk"}
    assert next(e for e in events if e.content == "Answer").parent_event_ids == [spans["llm"].id]


async def test_stream_failure_preserves_last_partial_batch(service, tmp_path):
    path = tmp_path / "broken.jsonl"
    rows = [{"type": "session", "harness": "test", "id": "s"}]
    rows += [
        {"type": "message", "message": {"role": "assistant", "content": str(i)}} for i in range(133)
    ]
    path.write_text("\n".join(map(json.dumps, rows)) + '\n{"broken":')
    ref = service.sources.resolve(source_ref(str(path))).ref
    workspace = await service.dispatch("workspaces.create", {"name": "partial"})
    await import_sources(service, Job(kind="import", name="test"), workspace["id"], [ref.wire()])
    await asyncio.gather(*list(service.jobs.tasks.values()))
    t = service.db.list("trajectories")[0]
    assert t["metadata"]["indexState"] == "ERROR"
    assert t["eventCount"] >= 133
    assert not t["loaded"] and not t["capabilities"]["classify"]
    assert service.db.query("SELECT COUNT(*) FROM events")[0][0] == t["eventCount"]
    with pytest.raises(ValueError, match="index"):
        await service.load_events(t["id"])
    await service.dispatch("sources.retry", {"trajectoryId": t["id"]})
    await asyncio.gather(*list(service.jobs.tasks.values()))
    assert service.db.query("SELECT COUNT(*) FROM events")[0][0] == t["eventCount"]


async def test_directory_bundle_retains_independent_agents_and_scores(service, tmp_path):
    directory = tmp_path / "run"
    directory.mkdir()
    for name in ("planner", "coder"):
        (directory / f"{name}.jsonl").write_text(
            json.dumps({"type": "session", "harness": "test", "id": name})
            + "\n"
            + json.dumps({"type": "message", "message": {"role": "assistant", "content": name}})
        )
    (directory / "scores.json").write_text('{"correct": 1}')
    (directory / "config.yaml").write_text("model: example\n")
    (directory / "artifacts").mkdir()
    ref = service.sources.resolve(source_ref(str(directory))).ref
    proposal = await service.dispatch("sources.bundle", {"ref": ref.wire()})
    assert len(proposal["streams"]) == 2 and len(proposal["artifacts"]) == 1
    workspace = await service.dispatch("workspaces.create", {"name": "bundle"})
    await import_bundle(service, Job(kind="import", name="test"), workspace["id"], ref.wire(), {})
    t = service.db.list("trajectories")[0]
    assert t["loaded"] and t["scores"] == {"correct": 1}
    assert t["capabilities"]["multiAgentGraph"] and t["capabilities"]["artifacts"]
    assert not t["capabilities"]["contextFork"]
    events = await service.load_events(t["id"])
    messages = [e for e in events if e["type"] == "assistant"]
    assert len(messages) == 2 and messages[0]["parentEventIds"] != messages[1]["parentEventIds"]
    timeline = await service.dispatch("timeline", {"trajectoryId": t["id"]})
    assert any(m.get("agent") for m in timeline["markers"])
