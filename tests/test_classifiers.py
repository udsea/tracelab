import asyncio

import pytest
from tracelab.classifiers.runner import ClassifierRunner, windows
from tracelab.models.domain import ClassifierDefinition, Job, ProviderSettings


class ProviderDouble:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0
        self.active = 0
        self.max_active = 0

    async def generate_structured(self, **kwargs):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.002)
        self.active -= 1
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return {"output": output, "raw": {"test": output}, "request": kwargs}


def definition(**kwargs):
    return ClassifierDefinition(
        id="c",
        name="Evidence",
        prompt="Find evidence",
        model="test-model",
        provider="test",
        scope="event",
        **kwargs,
    )


def valid(event_id="t:e0"):
    return {"score": 0.7, "rationale": "Observed", "evidence_event_ids": [event_id]}


def runner(service, events, provider, endpoint="http://localhost:8123/v1"):
    async def load(_):
        return events

    settings = ProviderSettings(
        id="test",
        name="Test",
        kind="openai_compatible",
        base_url=endpoint,
        api_key_env="UNUSED",
    )
    return ClassifierRunner(service.db, service.jobs, load, lambda _: (provider, settings))


async def test_invalid_json_retries_once_and_retains_both_raw_attempts(service, event_factory):
    provider = ProviderDouble(["```json\n{}\n```", valid()])
    job = Job(kind="classifier", name="test")
    await runner(service, [event_factory()], provider).run(job, definition(), ["t"])
    result = service.db.list("classifier_results")[0]
    assert provider.calls == 2
    assert result["output"]["score"] == 0.7
    assert len(result["provenance"]["attempts"]) == 2
    assert "t:e0" in result["provenance"]["prompt"]


@pytest.mark.parametrize(
    "output",
    [
        valid("wrong:e9"),
        {"score": 4},
        {"score": "0.7", "rationale": "text", "evidence_event_ids": []},
        {},
    ],
)
async def test_malformed_outputs_record_errors_without_repair(service, event_factory, output):
    provider = ProviderDouble([output, output])
    job = Job(kind="classifier", name="test")
    with pytest.raises(RuntimeError, match="1 of 1"):
        await runner(service, [event_factory()], provider).run(job, definition(), ["t"])
    result = service.db.list("classifier_results")[0]
    assert result["output"] is None
    assert result["error"]
    assert provider.calls == 2
    assert not service.db.list("cache")


async def test_transport_failure_does_not_trigger_output_retry(service, event_factory):
    provider = ProviderDouble([RuntimeError("HTTP 429")])
    with pytest.raises(RuntimeError):
        await runner(service, [event_factory()], provider).run(
            Job(kind="classifier", name="test"), definition(), ["t"]
        )
    assert provider.calls == 1


async def test_cache_respects_input_parameters_and_endpoint(service, event_factory):
    provider = ProviderDouble([valid()] * 8)
    definition_value = definition()
    events = [event_factory()]
    first = runner(service, events, provider)
    for _ in range(2):
        await first.run(Job(kind="classifier", name="test"), definition_value, ["t"])
    assert provider.calls == 1
    assert sum(r["cached"] for r in service.db.list("classifier_results")) == 1
    events[0]["content"] = "Changed input"
    await first.run(Job(kind="classifier", name="test"), definition_value, ["t"])
    assert provider.calls == 2
    definition_value.generation_parameters = {"temperature": 0.2}
    await first.run(Job(kind="classifier", name="test"), definition_value, ["t"])
    assert provider.calls == 3
    await runner(service, events, provider, "http://localhost:9000/v1").run(
        Job(kind="classifier", name="test"), definition_value, ["t"]
    )
    assert provider.calls == 4
    await first.run(Job(kind="classifier", name="test"), definition_value, ["t"], rerun=True)
    assert provider.calls == 5


async def test_bounded_workers_and_all_windows(service, event_factory):
    events = [event_factory(i) for i in range(31)]
    provider = ProviderDouble([{**valid(), "evidence_event_ids": []}] * 31)
    job = Job(kind="classifier", name="test", concurrency=3)
    await runner(service, events, provider).run(job, definition(), ["t"])
    assert 1 < provider.max_active <= 3
    assert job.completed == job.total == 31


def test_window_end_is_inclusive_and_stride_not_rewritten(event_factory):
    events = [event_factory(i) for i in range(9)]
    classifier = definition(window_size=4, stride=3)
    classifier.scope = "window"
    result = list(windows(events, classifier))
    assert [[e["index"] for e in w] for w in result] == [
        [0, 1, 2, 3],
        [3, 4, 5, 6],
        [6, 7, 8],
    ]


async def test_cancel_awaits_inflight_workers_and_preserves_results(service, event_factory):
    called = asyncio.Event()
    stopped = asyncio.Event()

    class SlowProvider:
        async def generate_structured(self, **kwargs):
            called.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    engine = runner(service, [event_factory()], SlowProvider())
    job = Job(kind="classifier", name="cancel")
    service.jobs.start(job, lambda j: engine.run(j, definition(), ["t"]))
    await asyncio.wait_for(called.wait(), 2)
    task = service.jobs.tasks[job.id]
    service.jobs.cancel(job.id)
    await task
    assert stopped.is_set()
    assert service.db.get("jobs", job.id)["status"] == "cancelled"
    assert not service.db.list("classifier_results")
