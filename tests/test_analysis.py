import copy

import pytest
from tracelab.comparison.service import compare_events, group_comparison, group_members
from tracelab.models.domain import (
    ClassifierOutput,
    ClassifierResult,
    Job,
    Segment,
    Trajectory,
)
from tracelab.segmentation.service import run_segmentation, validate_segments
from tracelab.storage.queries import event_page, list_trajectories, result_summaries


def seed_trajectories(service, event_factory):
    service.db.put("experiments", {"id": "exp", "workspaceId": "ws"})
    for index, status in enumerate(["success", "failure", "unknown", "error"]):
        t = Trajectory(
            id=f"t{index}",
            experiment_id="exp",
            sample_id=str(index),
            condition="A" if index < 2 else "B",
            status=status,
            total_tokens=index * 100,
            scores={"metric": {"value": index / 3}},
            event_count=4,
            loaded=True,
        )
        service.db.put("trajectories", t)
        service.db.put_many(
            "events",
            [
                event_factory(i, content=f"unique_{index}_{i} secret.txt", tid=t.id)
                for i in range(4)
            ],
        )


def test_filters_are_parameterized_and_combined(service, event_factory):
    seed_trajectories(service, event_factory)
    assert (
        list_trajectories(service.db, "ws", filters=[{"field": "status", "value": "success"}])[
            "total"
        ]
        == 1
    )
    assert (
        list_trajectories(
            service.db,
            "ws",
            filters=[
                {"field": "tokens", "op": "gt", "value": 100},
                {"field": "condition", "value": "B"},
            ],
        )["total"]
        == 2
    )
    assert (
        list_trajectories(
            service.db,
            "ws",
            filters=[{"field": "score", "key": "metric", "op": "gt", "value": 0.5}],
        )["total"]
        == 2
    )
    assert (
        list_trajectories(
            service.db, "ws", filters=[{"field": "condition", "value": "' OR TRUE --"}]
        )["total"]
        == 0
    )
    with pytest.raises(ValueError, match="Unsupported filter"):
        list_trajectories(
            service.db, "ws", filters=[{"field": "DROP TABLE trajectories", "value": "x"}]
        )


def test_sample_picker_paging_and_error_previews(service, event_factory):
    seed_trajectories(service, event_factory)
    page = list_trajectories(service.db, "ws", offset=2, limit=1)
    assert page["total"] == 4
    assert page["items"][0]["sampleId"] == "2"
    assert (
        list_trajectories(
            service.db, "ws", filters=[{"field": "sample", "op": "contains", "value": "2"}]
        )["items"][0]["id"]
        == "t2"
    )
    service.db.put(
        "events",
        event_factory(
            1,
            type="tool_result",
            content="",
            tid="t0",
            tool={"name": "write_file", "error": "Filesystem unavailable"},
        ),
    )
    errors = event_page(service.db, "t0", mode="errors")
    assert errors["total"] == 1
    assert errors["items"][0]["preview"] == "Filesystem unavailable"


def test_json_label_fork_and_error_filters_on_populated_data(service, event_factory):
    seed_trajectories(service, event_factory)
    child = service.db.get("trajectories", "t2")
    service.db.put("trajectories", child | {"forkId": "fork"})
    service.db.put("forks", {"id": "fork", "status": "complete"})
    service.db.put(
        "classifier_results",
        ClassifierResult(
            classifier_id="c",
            run_id="r",
            trajectory_id="t2",
            start_event_index=0,
            end_event_index=1,
            cache_key="label-filter",
            output=ClassifierOutput(label="possible"),
        ),
    )
    result = list_trajectories(
        service.db,
        "ws",
        filters=[
            {"field": "classifierLabel", "key": "c", "value": "possible"},
            {"field": "status", "value": "unknown"},
        ],
    )
    assert [item["id"] for item in result["items"]] == ["t2"]
    assert (
        list_trajectories(service.db, "ws", filters=[{"field": "forkStatus", "value": "complete"}])[
            "items"
        ][0]["id"]
        == "t2"
    )
    assert (
        list_trajectories(service.db, "ws", filters=[{"field": "error", "value": True}])["items"][
            0
        ]["id"]
        == "t3"
    )


async def test_search_annotation_range_and_lazy_event_summary(service, event_factory):
    seed_trajectories(service, event_factory)
    annotation = await service.dispatch(
        "annotations.save",
        {
            "trajectoryId": "t0",
            "startEventIndex": 1,
            "endEventIndex": 2,
            "label": "HARNESS_BUG",
            "note": "Distinctive annotation",
        },
    )
    search = await service.dispatch("search", {"workspaceId": "ws", "query": "Distinctive"})
    assert search["items"][0]["type"] == "annotation"
    assert search["items"][0]["index"] == 1
    assert (
        list_trajectories(
            service.db, "ws", filters=[{"field": "annotation", "value": "HARNESS_BUG"}]
        )["total"]
        == 1
    )
    with pytest.raises(ValueError, match="beyond"):
        await service.dispatch(
            "annotations.save",
            {"trajectoryId": "t0", "startEventIndex": 1, "endEventIndex": 99, "label": "BAD"},
        )
    await service.dispatch("annotations.delete", {"id": annotation["id"]})
    assert not service.db.list("annotations")
    results = await service.dispatch("search", {"workspaceId": "ws", "query": "secret.txt"})
    assert results["total"] == 16


def test_reruns_do_not_mix_versions_or_reweight_group_means(service, event_factory):
    seed_trajectories(service, event_factory)
    for tid, count, score in [("t0", 3, 0.9), ("t1", 1, 0.1)]:
        for index in range(count):
            service.db.put(
                "classifier_results",
                ClassifierResult(
                    classifier_id="c",
                    run_id="r1",
                    trajectory_id=tid,
                    start_event_index=index,
                    end_event_index=index,
                    cache_key=f"{tid}:{index}",
                    output=ClassifierOutput(score=score),
                    provenance={"prompt": "x" * 10000},
                ),
            )
    groups = group_comparison(service.db, "ws", [{"experimentId": "exp"}])
    assert groups[0]["classifiers"][0]["meanScore"] == pytest.approx(0.5)  # not .7
    assert groups[0]["scoredOutcomes"] == 2
    assert groups[0]["successRate"] == 0.5
    assert group_members(service.db, "ws", {}, "c")["total"] == 2
    assert all("provenance" not in r for r in result_summaries(service.db, "t0"))
    service.db.put(
        "classifier_results",
        ClassifierResult(
            classifier_id="c",
            run_id="r2",
            trajectory_id="t0",
            start_event_index=0,
            end_event_index=0,
            cache_key="new",
            output=None,
            error="malformed",
        ),
    )
    assert len(result_summaries(service.db, "t0")) == 1
    groups = group_comparison(service.db, "ws", [{}])
    assert groups[0]["classifiers"][0]["n"] == 1
    assert groups[0]["classifiers"][0]["meanScore"] == 0.1
    assert (
        list_trajectories(
            service.db,
            "ws",
            filters=[{"field": "classifier", "key": "c", "op": "gt", "value": 0.8}],
        )["total"]
        == 0
    )
    assert len(service.db.list("classifier_results")) == 5  # history retained


def test_divergence_is_distinct_from_intervention_and_handles_removal(event_factory):
    original = [event_factory(i, "assistant", str(i)) for i in range(7)]
    branch = copy.deepcopy(original)
    branch[2]["content"] = "intervened"
    branch[2]["metadata"]["intervened"] = True
    branch[5]["content"] = "different behavior"
    result = compare_events(original, branch, 2)
    assert result["commonPrefix"] == 2
    assert result["firstBehaviouralDivergence"] == {"left": 5, "right": 5}
    removed = compare_events(original, original[:2] + original[3:], 2)
    assert removed["commonPrefix"] == 2
    assert removed["firstBehaviouralDivergence"] is None
    assert sum(r["changed"] for r in removed["rows"]) == 1


@pytest.mark.parametrize(
    "segments",
    [
        [{"start_event": 0, "end_event": 2, "parent_phase": None}],
        [
            {"start_event": 0, "end_event": 3, "parent_phase": None},
            {"start_event": 1, "end_event": 2, "parent_phase": 9},
        ],
        [
            {"start_event": 0, "end_event": 3, "parent_phase": None},
            {"start_event": 1, "end_event": 5, "parent_phase": 0},
        ],
    ],
)
def test_segmentation_rejects_incomplete_ranges_and_bad_hierarchy(segments):
    with pytest.raises(ValueError):
        validate_segments(segments, 4)


async def test_segmentation_validates_before_replacing_and_caches_exact_prompt(
    service, event_factory
):
    from tracelab.models.domain import ProviderSettings

    seed_trajectories(service, event_factory)
    initial = Segment(trajectory_id="t0", start_event=0, end_event=3, label="Manual label")
    service.db.put("segments", initial)

    class Provider:
        def __init__(self):
            self.calls = 0
            self.output = {"segments": []}

        async def generate_structured(self, **kwargs):
            self.calls += 1
            return {"output": self.output, "raw": self.output, "request": kwargs}

    provider = Provider()
    settings = ProviderSettings(
        id="p",
        name="Test",
        kind="openai_compatible",
        base_url="http://localhost:1/v1",
        api_key_env="UNUSED",
    )
    service.provider_factory = lambda _: (provider, settings)
    with pytest.raises(ValueError):
        await run_segmentation(service, Job(kind="segmentation", name="test"), "t0", "p", "model")
    assert provider.calls == 2
    assert service.db.get("segments", initial.id)["label"] == "Manual label"
    provider.output = {
        "segments": [
            {
                "start_event": 0,
                "end_event": 3,
                "label": "Exploration",
                "summary": "Examining context",
                "confidence": 0.8,
                "parent_phase": None,
            }
        ]
    }
    for _ in range(2):
        await run_segmentation(service, Job(kind="segmentation", name="test"), "t0", "p", "model")
    assert provider.calls == 3
    assert service.db.list("segments")[0]["label"] == "Exploration"


async def test_provider_settings_reject_credentials_in_url(service):
    with pytest.raises(ValueError, match="embedded credentials"):
        await service.dispatch(
            "providers.save",
            {
                "id": "bad",
                "name": "bad",
                "kind": "openai_compatible",
                "baseUrl": "https://secret@example.com/v1",
                "apiKeyEnv": "KEY",
            },
        )
