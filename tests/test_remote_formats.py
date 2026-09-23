import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from test_sources import FakeHub, MeasuredFS
from tracelab.classifiers.runner import ClassifierRunner
from tracelab.importers.registry import choose
from tracelab.ingestion.universal import import_sources
from tracelab.models.domain import ClassifierDefinition, Job, ProviderSettings
from tracelab.segmentation.service import run_segmentation
from tracelab.sources.cache import RemoteCache
from tracelab.sources.huggingface import HuggingFaceSourceProvider
from tracelab.sources.refs import source_ref
from tracelab.sources.remote import HttpSourceProvider


@pytest.mark.parametrize(
    "expected,rows",
    [
        (
            "atif",
            [
                {
                    "schema_version": "ATIF-v1.8",
                    "session_id": "s",
                    "steps": [{"step_id": 1, "source": "agent", "message": "Answer"}],
                }
            ],
        ),
        (
            "atof",
            [
                {
                    "atof_version": "0.1",
                    "kind": "scope",
                    "scope_category": "start",
                    "uuid": "a",
                    "category": "agent",
                    "timestamp": 1700000000000000,
                }
            ],
        ),
        (
            "sts",
            [
                {"type": "session", "harness": "pi", "id": "s"},
                {"type": "message", "message": {"role": "assistant", "content": "Answer"}},
            ],
        ),
        (
            "generic",
            [
                {"event_type": "assistant", "text": "Answer"},
                {"event_type": "user", "text": "Continue"},
            ],
        ),
    ],
)
def test_remote_formats_share_normalizers(tmp_path, expected, rows):
    raw = "\n".join(map(json.dumps, rows)).encode()

    class Hub(FakeHub):
        def get_paths_info(self, *args, **kwargs):
            return [SimpleNamespace(path="run.jsonl", size=len(raw), blob_id="blob", lfs=None)]

    cache = RemoteCache(tmp_path)
    fs = MeasuredFS(raw)
    provider = HuggingFaceSourceProvider(cache, Hub(), fs)
    try:
        ref = provider.stat(source_ref("hf://datasets/org/repo/run.jsonl")).ref
        importer, _ = choose(provider, ref)
        assert importer.name == expected
        result = importer.load_trajectory(provider, importer.discover_runs(provider, ref)[0])
        assert result.events and all(e.metadata.get("raw") is not None for e in result.events)
        fs.offline = True
        assert (
            importer.load_trajectory(provider, importer.discover_runs(provider, ref)[0]).events
            == result.events
        )
        assert cache.transferred_bytes == len(raw)
    finally:
        cache.close()


def test_http_non_range_fallback_materializes_only_selected_file(tmp_path, monkeypatch):
    raw = b"x" * 200000
    seen = []

    def respond(request):
        seen.append((request.method, str(request.url)))
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(raw)), "ETag": '"v1"'},
            content=raw if request.method == "GET" else b"",
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx, "head", client.head)
    monkeypatch.setattr(httpx, "stream", client.stream)
    cache = RemoteCache(tmp_path)
    try:
        provider = HttpSourceProvider(cache)
        ref = provider.stat(source_ref("https://example.org/selected.jsonl")).ref
        assert provider.read_range(ref, 80000, 100000) == raw[80000:100000]
        assert cache.transferred_bytes == len(raw)
        assert provider.read_range(ref, 0, 10) == b"x" * 10
        provider.pin(ref)
        assert len([r for r in seen if r[0] == "GET"]) == 1
        assert cache.stats()["pinnedBytes"] >= len(raw)
        cache.clear()
        assert provider.read_range(ref, 199990, 200000) == b"x" * 10
    finally:
        cache.close()
        client.close()


async def test_normalized_sts_runs_existing_classifiers_segmentation_and_lanes(service, tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        '{"type":"session","harness":"test","id":"session"}\n{"type":"message","message":{"role":"assistant","content":"Answer"}}\n'
    )
    ref = service.sources.resolve(source_ref(str(path))).ref
    workspace = await service.dispatch("workspaces.create", {"name": "analysis"})
    await import_sources(service, Job(kind="import", name="test"), workspace["id"], [ref.wire()])
    await asyncio.gather(*list(service.jobs.tasks.values()))
    t = service.db.list("trajectories")[0]
    events = await service.load_events(t["id"])

    class Provider:
        async def generate_structured(self, **request):
            if "segments" in request["schema"]["properties"]:
                result = {
                    "segments": [
                        {
                            "start_event": 0,
                            "end_event": len(events) - 1,
                            "label": "Response",
                            "summary": "Recorded messages",
                            "confidence": 0.8,
                            "parent_phase": None,
                        }
                    ]
                }
            else:
                result = {
                    "score": 0.7,
                    "rationale": "Test result",
                    "evidence_event_ids": [events[-1]["id"]],
                }
            return {"output": result, "raw": result}

    settings = ProviderSettings(
        id="test",
        name="Test",
        kind="openai_compatible",
        base_url="http://localhost:1",
        api_key_env="UNUSED",
    )
    service.provider_factory = lambda _: (Provider(), settings)
    runner = ClassifierRunner(
        service.db, service.jobs, service.load_events, service.provider_factory
    )
    classifier = ClassifierDefinition(
        name="Example", prompt="Classify", provider="test", model="test", scope="trajectory"
    )
    await runner.run(Job(kind="classifier", name="test"), classifier, [t["id"]])
    await run_segmentation(service, Job(kind="segmentation", name="test"), t["id"], "test", "test")
    timeline = await service.dispatch("timeline", {"trajectoryId": t["id"]})
    assert timeline["results"][0]["output"]["score"] == 0.7
    assert timeline["segments"][0]["label"] == "Response"
    assert timeline["results"][0]["output"]["evidenceEventIds"] == [events[-1]["id"]]
