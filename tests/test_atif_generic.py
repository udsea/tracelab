import asyncio
import json

import pytest
from tracelab.importers.inference import infer
from tracelab.importers.registry import choose
from tracelab.ingestion.universal import import_sources
from tracelab.models.domain import Job
from tracelab.sources.local import LocalSourceProvider
from tracelab.sources.refs import source_ref


def test_atif_embedded_subagents_keep_identity_and_delegation(tmp_path):
    raw = {
        "schema_version": "ATIF-v1.8",
        "trajectory_id": "parent",
        "session_id": "session",
        "agent": {"name": "planner"},
        "steps": [
            {
                "step_id": 1,
                "source": "agent",
                "message": "Delegate",
                "reasoning_content": "Need independent check",
                "tool_calls": [
                    {"tool_call_id": "call", "function_name": "delegate", "arguments": {}}
                ],
                "observation": {
                    "results": [
                        {
                            "source_call_id": "call",
                            "content": "Done",
                            "subagent_trajectory_ref": [
                                {"trajectory_id": "child", "trajectory_path": None}
                            ],
                        }
                    ]
                },
            }
        ],
        "subagent_trajectories": [
            {
                "schema_version": "ATIF-v1.8",
                "trajectory_id": "child",
                "session_id": "session",
                "agent": {"name": "coder"},
                "steps": [
                    {
                        "step_id": 1,
                        "source": "agent",
                        "message": "Child answer",
                        "metrics": {"prompt_tokens": 8},
                    }
                ],
                "extra": {"unknown": "kept"},
            }
        ],
        "continued_trajectory_ref": "next.json",
        "custom": {"also": "retained"},
    }
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(raw))
    source = LocalSourceProvider()
    ref = source.stat(source_ref(str(path))).ref
    importer, _ = choose(source, ref)
    assert importer.name == "atif"
    events = importer.load_trajectory(source, importer.discover_runs(source, ref)[0]).events
    scopes = {
        e.metadata.get("trajectoryIdentity"): e
        for e in events
        if e.metadata.get("trajectoryIdentity")
    }
    assert scopes["parent"].id in scopes["child"].parent_event_ids
    call = next(e for e in events if e.type == "tool_call")
    assert call.id in scopes["child"].parent_event_ids
    observation = next(e for e in events if e.type == "tool_result")
    assert scopes["child"].id in observation.parent_event_ids
    child_answer = next(e for e in events if e.content == "Child answer")
    assert child_answer.metadata["agentId"] == "child"
    assert events[-1].metadata["raw"]["custom"] == {"also": "retained"}
    assert events[-1].metadata["continuation"] == "next.json"


async def test_generic_requires_review_then_reuses_structural_fingerprint(service, tmp_path):
    workspace = await service.dispatch("workspaces.create", {"name": "Generic"})
    provider = LocalSourceProvider()
    paths = []
    for index in range(2):
        path = tmp_path / f"run{index}.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "run_id": f"run-{index}",
                        "worker": "agent-A",
                        "type": "assistant",
                        "content": f"Answer {index}.{j}",
                        "timestamp": 1700000000000 + j,
                    }
                )
                for j in range(3)
            )
        )
        paths.append(provider.stat(source_ref(str(path))).ref)
    first = infer(provider, paths[0])
    second = infer(provider, paths[1])
    assert first["fingerprint"] == second["fingerprint"]
    with pytest.raises(ValueError, match="requires review"):
        await import_sources(
            service, Job(kind="import", name="test"), workspace["id"], [paths[0].wire()]
        )
    assert service.db.list("experiments") == []
    for index, ref in enumerate(paths):
        approval = (
            {ref.uri: {"fingerprint": first["fingerprint"], "mapping": first["mapping"]}}
            if index == 0
            else None
        )
        await import_sources(
            service, Job(kind="import", name="test"), workspace["id"], [ref.wire()], approval
        )
        await asyncio.gather(*list(service.jobs.tasks.values()))
    trajectories = service.db.list("trajectories")
    assert len(trajectories) == 2 and all(t["loaded"] for t in trajectories)
    assert all(t["eventCount"] == 3 for t in trajectories)
    assert (await service.dispatch("sources.detect", {"ref": paths[1].wire()}))[
        "knownProfile"
    ] is True
    for trajectory in trajectories:
        events = await service.load_events(trajectory["id"])
        assert events[0]["metadata"]["agentId"] == "agent-A"
        assert events[0]["metadata"]["raw"]["run_id"] == trajectory["sampleId"]


async def test_schema_assistance_is_never_implicit(service, tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text('{"role":"assistant","content":"private"}\n')
    ref = LocalSourceProvider().stat(source_ref(str(path))).ref
    with pytest.raises(ValueError, match="explicit action"):
        await service.dispatch(
            "sources.assist", {"ref": ref.wire(), "provider": "openai", "model": "test"}
        )
