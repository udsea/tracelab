"""Opt-in public, immutable corpus acceptance. Never calls a model API."""

import asyncio
import os

import pytest
from tracelab.api.service import Service
from tracelab.ingestion.universal import import_sources
from tracelab.models.domain import Job
from tracelab.sources.refs import child_ref

pytestmark = pytest.mark.skipif(
    os.environ.get("TRACELAB_REMOTE_TESTS") != "1",
    reason="Set TRACELAB_REMOTE_TESTS=1 for public corpus reads",
)
REPO = "aisa-group/instrumental-choices-agent-traces"
SHA = "c5c77cd662316e609515dcdee5131788dd724258"
LOG = "inspect_logs/openrouter_google_gemini-3-flash-preview_exacto/repeat_02/2026-04-26T09-27-46+00-00_quota-boost-task_mMZW3mjR5wWsH5hj3YPQqn.eval"
STS = "viewer_sessions/openrouter_minimax_minimax-m2.7_exacto/repeat_02/quota_boost_G.jsonl"


async def test_public_hf_inspect_lazy_samples_restart_and_pin(tmp_path, monkeypatch):
    from tracelab.models.domain import SourceRef

    data = tmp_path / "app"
    service = Service(data)
    try:
        root = await service.dispatch(
            "sources.connect", {"uri": REPO, "kind": "huggingface", "revision": SHA}
        )
        root = SourceRef.model_validate(root["ref"])
        entries = await service.dispatch("sources.list", {"ref": root.wire()})
        assert any(e["name"] == "inspect_logs" for e in entries)
        assert service.sources.cache.transferred_bytes == 0
        ref = service.sources.resolve(child_ref(root, LOG)).ref
        workspace = await service.dispatch("workspaces.create", {"name": "Remote acceptance"})
        await import_sources(
            service, Job(kind="import", name="remote"), workspace["id"], [ref.wire()]
        )
        trajectories = service.db.list("trajectories")
        assert len(trajectories) == 8 and not any(t["loaded"] for t in trajectories)
        header_bytes = service.sources.cache.transferred_bytes
        assert 0 < header_bytes < ref.size_bytes
        first = trajectories[0]["id"]
        opened = await service.dispatch("trajectories.get", {"id": first})
        assert opened["trajectory"]["eventCount"] > 0
        assert sum(t["loaded"] for t in service.db.list("trajectories")) == 1
        assert (await service.dispatch("timeline", {"trajectoryId": first}))["markers"]
        assert service.sources.cache.transferred_bytes <= ref.size_bytes
        print(
            f"\nHF listing file-content bytes=0; header+summaries={header_bytes}; selected sample={service.sources.cache.transferred_bytes}; file={ref.size_bytes}"
        )
    finally:
        await service.close()
    service = Service(data)
    try:
        assert (await service.dispatch("trajectories.get", {"id": first}))["trajectory"]["loaded"]
        assert service.sources.cache.transferred_bytes == 0
        await service.dispatch("trajectories.get", {"id": trajectories[1]["id"]})
        pinned = await service.dispatch("sources.pin", {"ref": ref.wire(), "trajectoryId": first})
        await asyncio.gather(*list(service.jobs.tasks.values()))
        assert service.db.get("jobs", pinned["id"])["status"] == "complete"

        def offline(*args, **kwargs):
            raise OSError("Test disconnected network")

        provider = service.sources.provider(ref)
        monkeypatch.setattr(provider, "fetch_range", offline)
        monkeypatch.setattr(provider.api, "get_paths_info", offline)
        # A previously unopened sample must also work from the pinned selected file.
        assert (await service.dispatch("trajectories.get", {"id": trajectories[2]["id"]}))[
            "trajectory"
        ]["loaded"]
    finally:
        await service.close()


async def test_public_hf_session_trace(service):
    from tracelab.sources.refs import source_ref

    ref = service.sources.resolve(
        child_ref(source_ref(REPO, kind="huggingface", revision=SHA), STS)
    ).ref
    workspace = await service.dispatch("workspaces.create", {"name": "STS corpus"})
    detection = await service.dispatch("sources.detect", {"ref": ref.wire()})
    assert detection["detections"][0]["format"] == "sts"
    await import_sources(service, Job(kind="import", name="STS"), workspace["id"], [ref.wire()])
    await asyncio.gather(*list(service.jobs.tasks.values()))
    t = service.db.list("trajectories")[0]
    assert t["loaded"] and t["eventCount"] > 1
    assert not t["capabilities"]["contextFork"]


async def test_budget_siphon_presentation_and_filtered_navigation(service):
    """Real Gemini regression; pinned source, no model invocation and no vendored corpus."""
    import json

    from tracelab.analysis.semantic import semantic_events
    from tracelab.classifiers.runner import classifier_input
    from tracelab.sources.refs import source_ref

    path = "inspect_logs/openrouter_google_gemini-3.1-pro-preview_exacto/repeat_01/2026-04-26T08-28-50+00-00_budget-siphon-task_hv8xPLk3QXDSGp5gdG98dC.eval"
    ref = child_ref(source_ref(REPO, kind="huggingface", revision=SHA), path)
    workspace = await service.dispatch("workspaces.create", {"name": "Presentation regression"})
    await import_sources(service, Job(kind="import", name="remote"), workspace["id"], [ref.wire()])
    trajectory = next(
        t for t in service.db.list("trajectories") if t["sampleId"] == "budget_siphon_H"
    )
    tid = trajectory["id"]
    loaded = await service.dispatch("trajectories.get", {"id": tid})
    assert loaded["eventCounts"] == {
        "recorded": 309,
        "research": 221,
        "semantic": 207,
        "runtime": 88,
        "opaque": 14,
    }
    for mode, offset in [("reasoning", 5), ("all", 53)]:
        location = await service.dispatch(
            "events.locate", {"trajectoryId": tid, "mode": mode, "eventIndex": 70}
        )
        assert location["exact"] and location["offset"] == offset
        page = await service.dispatch(
            "events.list", {"trajectoryId": tid, "mode": mode, "offset": offset, "limit": 1}
        )
        assert page["items"][0]["index"] == 70
        assert page["items"][0]["reasoningVisibility"] == "redacted"
        assert not page["items"][0]["preview"]
    event = (await service.dispatch("events.get", {"trajectoryId": tid, "index": 70}))["event"]
    assert event["content"] is None
    raw = await service.dispatch("events.raw", {"id": event["id"]})
    block = raw["raw"]["output"]["choices"][0]["message"]["content"][0]
    assert block["redacted"] is True and len(block["reasoning"]) == 144
    payload = block["reasoning"]
    events = await service.load_events(tid)
    assert payload not in json.dumps(classifier_input(events))
    assert payload not in json.dumps([e.wire() for e in semantic_events(events)])
    assert payload not in json.dumps(event)
    assert (await service.dispatch("search", {"workspaceId": workspace["id"], "query": payload}))[
        "total"
    ] == 0
    assert sum(t["loaded"] for t in service.db.list("trajectories")) == 1
    print(
        "\nBudget siphon: 309 recorded / 221 research / 88 runtime; #70 Reasoning offset 5, All offset 53; raw redacted payload retained"
    )
