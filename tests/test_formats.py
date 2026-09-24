import asyncio
import json

from tracelab.importers.registry import choose
from tracelab.ingestion.universal import import_sources
from tracelab.models.domain import Job
from tracelab.sources.local import LocalSourceProvider
from tracelab.sources.refs import source_ref


def write_lines(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows))
    return LocalSourceProvider().stat(source_ref(str(path))).ref


def test_atof_scopes_remain_a_graph_and_preserve_unknown_data(tmp_path):
    ref = write_lines(
        tmp_path / "arbitrary.extension",
        [
            {
                "atof_version": "0.1",
                "kind": "scope",
                "scope_category": "start",
                "uuid": "agent",
                "parent_uuid": None,
                "category": "agent",
                "timestamp": 1700000000000000,
                "name": "planner",
            },
            {
                "atof_version": "0.1",
                "kind": "scope",
                "scope_category": "start",
                "uuid": "tool",
                "parent_uuid": "agent",
                "category": "tool",
                "name": "read",
                "data": {"path": "x"},
                "custom": "retained",
            },
            {
                "atof_version": "0.1",
                "kind": "scope",
                "scope_category": "end",
                "uuid": "tool",
                "parent_uuid": "agent",
                "category": "tool",
                "name": "read",
                "data": "result",
            },
        ],
    )
    provider = LocalSourceProvider()
    importer, _ = choose(provider, ref)
    assert importer.name == "atof"
    events = importer.load_trajectory(provider, importer.discover_runs(provider, ref)[0]).events
    assert events[0].id in events[1].parent_event_ids
    assert events[1].id in events[2].parent_event_ids
    assert events[0].timestamp.startswith("2023-")
    assert events[1].metadata["raw"]["custom"] == "retained"


async def test_sts_normalized_events_work_with_existing_index_and_search(service, tmp_path):
    ref = write_lines(
        tmp_path / "session.jsonl",
        [
            {"type": "session", "id": "session-1", "harness": "example", "extra": 42},
            {"type": "message", "message": {"role": "user", "content": "Read secret.txt"}},
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoningContent": "Need to inspect",
                    "toolCalls": [{"id": "c", "function": {"name": "read", "arguments": "{}"}}],
                },
            },
            {
                "type": "message",
                "message": {"role": "tool", "toolCallId": "c", "content": "File result"},
            },
        ],
    )
    workspace = await service.dispatch("workspaces.create", {"name": "Formats"})
    await import_sources(service, Job(kind="import", name="test"), workspace["id"], [ref.wire()])
    await asyncio.gather(*list(service.jobs.tasks.values()))
    trajectories = await service.dispatch("trajectories.list", {"workspaceId": workspace["id"]})
    trajectory = trajectories["items"][0]
    assert trajectory["loaded"] and trajectory["metadata"]["indexState"] == "READY"
    events = await service.load_events(trajectory["id"])
    assert [e["type"] for e in events] == [
        "environment",
        "user",
        "reasoning",
        "tool_call",
        "tool_result",
    ]
    assert events[-2]["id"] in events[-1]["parentEventIds"]
    assert trajectory["capabilities"]["contextFork"] is False
    assert (
        await service.dispatch("search", {"workspaceId": workspace["id"], "query": "secret.txt"})
    )["total"] == 1
    selected = await service.dispatch("events.get", {"trajectoryId": trajectory["id"], "index": 0})
    assert "raw" not in selected["event"]["metadata"]
    raw = await service.dispatch("events.raw", {"id": selected["event"]["id"]})
    assert raw["extra"] == 42
