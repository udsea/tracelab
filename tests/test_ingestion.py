import hashlib

import pytest
from tracelab.ingestion.service import import_logs
from tracelab.inspect_adapter.demo import demo_log
from tracelab.models.domain import Job, Workspace


async def test_real_eval_incremental_import_and_source_immutability(service, tmp_path):
    source = tmp_path / "source.eval"
    demo_log(source, "baseline", [83, 84])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    workspace = Workspace(name="test")
    service.db.put("workspaces", workspace)
    job = Job(kind="import", name="import")
    await import_logs(service, job, workspace.id, str(source))
    items = (await service.dispatch("trajectories.list", {"workspaceId": workspace.id}))["items"]
    assert len(items) == 2
    assert not any(t["loaded"] for t in items)
    assert all(t["status"] == "unknown" for t in items)  # eval success != task success
    assert service.db.query("SELECT count(*) FROM events")[0][0] == 0
    page = await service.dispatch(
        "events.list", {"trajectoryId": items[0]["id"], "offset": 180, "limit": 10}
    )
    assert page["total"] == 487
    assert [e["index"] for e in page["items"]] == list(range(180, 190))
    assert "metadata" not in page["items"][0]  # No eager raw payloads
    loaded = service.db.list("trajectories")
    assert sum(t["loaded"] for t in loaded) == 1
    await import_logs(service, job, workspace.id, str(source))
    assert len(service.db.list("trajectories")) == 2
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    raw = await service.dispatch("events.raw", {"id": page["items"][0]["id"]})
    assert raw["raw"]


async def test_changed_log_versions_without_overwriting_analysis(service, tmp_path):
    source = tmp_path / "source.eval"
    demo_log(source, "baseline", [83])
    workspace = Workspace(name="test")
    service.db.put("workspaces", workspace)
    job = Job(kind="import", name="import")
    await import_logs(service, job, workspace.id, str(source))
    original = service.db.list("trajectories")[0]
    demo_log(source, "updated", [83, 84])
    with pytest.raises(ValueError, match="changed since indexing"):
        await service.load_events(original["id"])
    await import_logs(service, job, workspace.id, str(source))
    assert len(service.db.list("experiments")) == 2
    assert len(service.db.list("trajectories")) == 3


async def test_demo_is_labelled_synthetic_and_has_linked_evidence(service):
    workspace = await service.dispatch("workspaces.demo", {})
    assert workspace["isDemo"]
    trajectories = (await service.dispatch("trajectories.list", {"workspaceId": workspace["id"]}))[
        "items"
    ]
    assert len(trajectories) == 6
    assert all(t["eventCount"] == 487 for t in trajectories)
    timeline = await service.dispatch("timeline", {"trajectoryId": trajectories[0]["id"]})
    assert len(timeline["segments"]) == 5
    assert len(timeline["results"]) == 98
    result = await service.dispatch("results.get", {"id": timeline["results"][0]["id"]})
    assert result["provenance"]["synthetic"]
    for id in result["output"]["evidenceEventIds"]:
        assert service.db.get("events", id)
