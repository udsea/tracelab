import asyncio
import copy

import pytest
from test_fork_replay import SPEC, output, source_sample
from tracelab.api.service import Service
from tracelab.experiments.models import ForkExperimentSpec
from tracelab.inspect_adapter.normalize import normalize_sample
from tracelab.models.domain import Experiment, Trajectory, Workspace


async def design(service, replications=3):
    service.db.put("workspaces", Workspace(id="ws", name="Research"))
    service.db.put(
        "experiments",
        Experiment(id="source", workspace_id="ws", name="Source", source_path="fixture"),
    )
    cases = []
    for name in ("A", "B"):
        events, records = normalize_sample(name, source_sample())
        service.db.put(
            "trajectories",
            Trajectory(
                id=name,
                experiment_id="source",
                sample_id=name,
                model="mock-model",
                loaded=True,
                event_count=len(events),
            ),
        )
        service.db.put_many("events", events)
        service.db.put_many("source_records", records)
        cases.append(
            dict(
                id=name,
                sourceTrajectoryId=name,
                sourceEventId=events[0].id,
                arms=[
                    dict(armId="control", interventions=[]),
                    dict(
                        armId="treatment",
                        interventions=[
                            dict(
                                type="replace_content", eventId=events[0].id, content="Edited task"
                            )
                        ],
                    ),
                ],
            )
        )
    return dict(
        workspaceId="ws",
        name="Remove evaluator hint",
        arms=[
            dict(id="control", name="Control", role="control"),
            dict(id="treatment", name="Treatment", role="treatment"),
        ],
        cases=cases,
        replicationCount=replications,
        executionSpec=SPEC,
        modelOverrides=dict(provider="local", model="mock-model", parameters={"seed": 50}),
    )


def fake(service, *, fail_at=None, pause_at=None):
    seen = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def run(request):
        current = request["execution"].trajectory
        seen.append(copy.deepcopy(current.metadata))
        # Every scheduler row exists before the first provider invocation.
        assert len(service.db.list("fork_trials")) == len(
            service.db.list("fork_experiments")[0]["trialIds"]
        )
        execution = request["execution"]
        execution.start_step()
        execution.on_output(output(("a", "read_file", {"path": "a.txt"})))
        if len(seen) == pause_at:
            entered.set()
            await release.wait()
        if len(seen) == fail_at:
            raise RuntimeError("provider unavailable")
        execution.start_step()
        # Treatment is a valid policy stop, not a task failure.
        execution.on_output(
            output(("x", "delete_file", {"path": "a.txt"}))
            if current.metadata["experimentArmId"] == "treatment"
            else output(text="done")
        )
        return dict(sample={}, logPath="fake-log")

    service.adapter.run_fork = run
    return seen, entered, release


async def finish(service, result):
    await service.jobs.tasks[result["job"]["id"]]
    await asyncio.gather(*list(service.jobs.tasks.values()))
    return await service.dispatch("forkExperiments.get", {"id": result["experimentId"]})


async def test_matrix_schedule_seed_binding_policy_and_analysis(service):
    request = await design(service)
    seen, _, _ = fake(service)
    execute_replication = service.forks.run_replication
    invoked = []

    async def checked_replication(*args, **kwargs):
        assert len(service.db.list("fork_trials")) == 12
        assert len(service.db.list("forks")) == 4
        if not invoked:
            assert len(service.db.list("trajectories")) == 2
        invoked.append(args[1])
        return await execute_replication(*args, **kwargs)

    service.forks.run_replication = checked_replication
    before = {
        t: copy.deepcopy(service.db.list(t))
        for t in (
            "forks",
            "fork_trials",
            "fork_experiments",
            "trajectories",
            "events",
            "source_records",
        )
    }
    preview = await service.dispatch("forkExperiments.preview", request)
    assert preview["allSupported"] and preview["totalTrials"] == 12 and len(preview["cells"]) == 4
    assert before == {t: service.db.list(t) for t in before}
    result = await service.dispatch(
        "forkExperiments.run", {**request, "expectedSpecHash": preview["specHash"]}
    )
    detail = await finish(service, result)
    assert detail["experiment"]["status"] == "complete"
    assert detail["progress"]["complete"] == 12
    assert len(service.db.list("forks")) == 4
    assert [(t["caseId"], t["armId"], t["replicationIndex"]) for t in detail["trials"]] == [
        (c, a, r)
        for r in range(3)
        for i, c in enumerate(("A", "B"))
        for a in (("control", "treatment") if (i + r) % 2 == 0 else ("treatment", "control"))
    ]
    assert len(seen) == len(invoked) == 12
    for trial in detail["trials"]:
        child = service.db.get("trajectories", trial["childTrajectoryId"])
        m = child["metadata"]
        assert (
            trial["requestedSeed"]
            == m["requestedSeed"]
            == m["parameters"]["seed"]
            == 50 + trial["replicationIndex"]
        )
        assert trial["pairKey"] == m["pairKey"] == f"{trial['caseId']}:r{trial['replicationIndex']}"
        assert trial["scheduleOrdinal"] == m["scheduleOrdinal"]
        assert trial["status"] == "complete" and not trial["error"]
        if trial["armId"] == "treatment":
            assert child["status"] == "unknown" and m["terminationReason"] == "unmatched_tool_call"
        fork = service.db.get("forks", trial["forkId"])
        assert fork["status"] == "complete" and len(fork["childTrajectoryIds"]) == 3
        assert fork["metadata"]["inputHash"] and fork["metadata"]["inspectVersion"]
        assert (
            fork["interventions"]
            == request["cases"][0 if trial["caseId"] == "A" else 1]["arms"][
                0 if trial["armId"] == "control" else 1
            ]["interventions"]
        )
    assert len({t["pairKey"] for t in detail["trials"]}) == 6
    analysis = [j for j in service.db.list("jobs") if j["kind"] == "analysis"]
    assert len(analysis) == 1 and analysis[0]["status"] == "complete"
    assert not service.db.list("classifier_runs")
    assert len(service.db.list("branch_comparisons")) == 12
    assert len(await service.dispatch("experiments.list", {"workspaceId": "ws"})) == 1
    assert len(await service.dispatch("forkExperiments.list", {"workspaceId": "ws"})) == 1
    assert not await service.dispatch("forkExperiments.list", {"workspaceId": "other"})
    assert (
        len(
            await service.dispatch(
                "forkExperiments.trials",
                {
                    "experimentId": result["experimentId"],
                    "caseId": "A",
                    "armId": "control",
                    "limit": 2,
                },
            )
        )
        == 2
    )


async def test_provider_error_continues_and_analysis_failure_independent(service, monkeypatch):
    request = await design(service, 1)
    seen, _, _ = fake(service, fail_at=2)
    from tracelab.analysis import branches

    async def broken(*args):
        raise RuntimeError("analysis failed")

    monkeypatch.setattr(branches, "analyze_branches", broken)
    result = await service.dispatch("forkExperiments.run", request)
    detail = await finish(service, result)
    assert len(seen) == 4 and detail["experiment"]["status"] == "partial"
    assert detail["progress"]["error"] == 1 and detail["progress"]["complete"] == 3
    assert (
        service.db.get("jobs", detail["experiment"]["metadata"]["analysisJobId"])["status"]
        == "failed"
    )
    assert detail["trials"][1]["status"] == "error"
    assert (
        service.db.get("trajectories", detail["trials"][1]["childTrajectoryId"])["status"]
        == "error"
    )
    with pytest.raises(ValueError, match="No pending"):
        await service.dispatch("forkExperiments.resume", {"id": result["experimentId"]})


async def test_cancel_resume_and_restart_persist_only_pending(service):
    request = await design(service, 1)
    seen, entered, _ = fake(service, pause_at=2)
    result = await service.dispatch("forkExperiments.run", request)
    await asyncio.wait_for(entered.wait(), 10)
    await service.dispatch("jobs.cancel", {"id": result["job"]["id"]})
    detail = await finish(service, result)
    assert [t["status"] for t in detail["trials"]] == [
        "complete",
        "cancelled",
        "pending",
        "pending",
    ]
    assert detail["experiment"]["status"] == "cancelled"
    assert service.db.get("jobs", result["job"]["id"])["completed"] == 2
    partial = service.db.get("trajectories", detail["trials"][1]["childTrajectoryId"])
    assert partial["status"] == "cancelled" and partial["eventCount"] > 1
    old = [
        copy.deepcopy(service.db.get("trajectories", t["childTrajectoryId"]))
        for t in detail["trials"][:2]
    ]
    seen2, _, _ = fake(service)
    resumed = await service.dispatch("forkExperiments.resume", {"id": result["experimentId"]})
    final = await finish(service, resumed)
    assert resumed["job"]["id"] != result["job"]["id"]
    assert len(seen2) == 2 and len(seen) == 2
    assert final["experiment"]["status"] == "partial"
    assert old == [service.db.get("trajectories", c["id"]) for c in old]
    assert len(final["experiment"]["metadata"]["jobIds"]) == 2


async def test_restart_reconciles_interrupted_and_resume(tmp_path):
    path = tmp_path / "restart"
    service = Service(path)
    request = await design(service, 1)
    fake(service)
    result = await service.dispatch("forkExperiments.run", request)
    await finish(service, result)
    trials = service.fork_experiments.trials(result["experimentId"])
    original_child = trials[0].child_trajectory_id
    interrupted_child = trials[1].child_trajectory_id
    child = service.db.get("trajectories", interrupted_child)
    child["status"] = "running"
    child["metadata"]["executionStatus"] = "running"
    service.db.put("trajectories", child)
    interrupted_job = service.db.get("jobs", result["job"]["id"])
    interrupted_job.update(status="running", completed=1)
    service.db.put("jobs", interrupted_job)
    # Persist a crash snapshot: one finished, one active, two never started.
    for i, trial in enumerate(trials):
        trial.status = "complete" if i == 0 else "running" if i == 1 else "pending"
        if i > 0:
            trial.child_trajectory_id = None
        service.db.put("fork_trials", trial)
    exp = service.db.get("fork_experiments", result["experimentId"])
    exp["status"] = "running"
    service.db.put("fork_experiments", exp)
    await service.close()
    service = Service(path)
    try:
        detail = await service.dispatch("forkExperiments.get", {"id": result["experimentId"]})
        assert detail["experiment"]["status"] == "partial"
        assert [t["status"] for t in detail["trials"]] == [
            "complete",
            "interrupted",
            "pending",
            "pending",
        ]
        assert not service.jobs.tasks
        assert detail["trials"][1]["childTrajectoryId"] == interrupted_child
        assert (
            service.db.get("trajectories", interrupted_child)["metadata"]["executionStatus"]
            == "error"
        )
        assert service.db.get("jobs", result["job"]["id"])["completed"] == 2
        seen, _, _ = fake(service)
        final = await finish(
            service,
            await service.dispatch("forkExperiments.resume", {"id": result["experimentId"]}),
        )
        assert len(seen) == 2 and final["trials"][0]["childTrajectoryId"] == original_child
        assert final["trials"][1]["status"] == "interrupted"
    finally:
        await service.close()


@pytest.mark.parametrize("problem", ["foreign_target", "workspace", "schema"])
async def test_fail_closed_preflight_and_hash(service, problem):
    request = await design(service)
    seen, _, _ = fake(service)
    if problem == "foreign_target":
        request["cases"][1]["arms"][1]["interventions"][0]["eventId"] = "A:e0"
    elif problem == "workspace":
        row = service.db.get("experiments", "source")
        row["workspaceId"] = "other"
        service.db.put("experiments", row)
    else:
        for row in service.db.list("source_records", "trajectory_id=?", ["B"]):
            row["raw"].pop("tools", None)
            service.db.put("source_records", row)
    preview = await service.dispatch("forkExperiments.preview", request)
    assert not preview["allSupported"] and len(preview["cells"]) == 4
    result = await service.dispatch("forkExperiments.run", request)
    assert not result["started"]
    for table in ("forks", "fork_trials", "fork_experiments", "jobs"):
        assert not service.db.list(table)
    assert not seen and len(service.db.list("trajectories")) == 2


async def test_changed_preview_duplicate_design_and_limits(service):
    request = await design(service)
    preview = await service.dispatch("forkExperiments.preview", request)
    with pytest.raises(ValueError, match="changed since preview"):
        await service.dispatch(
            "forkExperiments.run",
            {**request, "replicationCount": 2, "expectedSpecHash": preview["specHash"]},
        )
    for patch in (
        {"replicationCount": 101},
        {"arms": [request["arms"][0]] * 2},
        {"cases": [request["cases"][0]] * 2},
    ):
        with pytest.raises(ValueError):
            ForkExperimentSpec.model_validate({**request, **patch})
    request["cases"][0]["arms"][1]["armId"] = "control"
    with pytest.raises(ValueError):
        ForkExperimentSpec.model_validate(request)


async def test_immediate_cancel_keeps_pending(service):
    request = await design(service)
    seen, _, _ = fake(service)
    result = await service.dispatch("forkExperiments.run", request)
    await service.dispatch("jobs.cancel", {"id": result["job"]["id"]})
    detail = await finish(service, result)
    assert detail["experiment"]["status"] == "cancelled"
    assert service.db.get("jobs", result["job"]["id"])["status"] == "cancelled"
    assert not seen
    assert detail["progress"]["pending"] > 0


async def test_single_turn_serial_execution_and_concrete_fork_immutability(service):
    request = await design(service, 1)
    request["executionSpec"] = {}
    active = peak = 0
    seen = []

    async def adapter(params):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        seen.append(params["sample_id"])
        await asyncio.sleep(0.01)
        active -= 1
        return dict(sample={"output": output(text="Done")}, logPath="fake")

    service.adapter.run_fork = adapter
    first = await service.dispatch("forkExperiments.run", request)
    second = await service.dispatch("forkExperiments.run", {**request, "name": "Another design"})
    await asyncio.gather(finish(service, first), finish(service, second))
    assert peak == 1 and len(seen) == 8
    detail = await service.dispatch("forkExperiments.get", {"id": first["experimentId"]})
    assert detail["usage"]["modelSteps"] == 4
    fork = service.db.list("forks")[0]
    with pytest.raises(ValueError, match="immutable"):
        await service.dispatch("forks.run", fork)


async def test_explicit_arm_seed_override_and_hash_identity(service):
    request = await design(service, 2)
    for case in request["cases"]:
        case["arms"][1]["interventions"].append(
            dict(type="generation_override", parameters={"seed": 70})
        )
    fake(service)
    preview1 = await service.dispatch("forkExperiments.preview", request)
    preview2 = await service.dispatch("forkExperiments.preview", copy.deepcopy(request))
    assert preview1 == preview2
    changed = copy.deepcopy(request)
    changed["cases"][0]["arms"][1]["interventions"][0]["content"] = "Different"
    assert (await service.dispatch("forkExperiments.preview", changed))["specHash"] != preview1[
        "specHash"
    ]
    final = await finish(service, await service.dispatch("forkExperiments.run", request))
    for trial in final["trials"]:
        assert (
            trial["requestedSeed"]
            == (50 if trial["armId"] == "control" else 70) + trial["replicationIndex"]
        )


async def test_thirty_trial_acceptance_matrix(service):
    request = await design(service, 5)
    events, records = normalize_sample("C", source_sample())
    service.db.put(
        "trajectories",
        Trajectory(
            id="C",
            experiment_id="source",
            sample_id="C",
            model="mock-model",
            loaded=True,
            event_count=len(events),
        ),
    )
    service.db.put_many("events", events)
    service.db.put_many("source_records", records)
    request["cases"].append(
        dict(
            id="C",
            sourceTrajectoryId="C",
            sourceEventId="C:e0",
            arms=[
                dict(armId="control", interventions=[]),
                dict(
                    armId="treatment",
                    interventions=[
                        dict(type="append_message", role="user", content="Check your work")
                    ],
                ),
            ],
        )
    )
    fake(service, fail_at=30)
    preview = await service.dispatch("forkExperiments.preview", request)
    assert len(preview["cells"]) == 6 and preview["totalTrials"] == 30
    final = await finish(service, await service.dispatch("forkExperiments.run", request))
    assert len(service.db.list("forks")) == 6 and len(service.db.list("fork_trials")) == 30
    assert final["progress"]["complete"] == 29 and final["progress"]["error"] == 1
    assert sorted(c["progress"]["complete"] for c in final["cells"]) == [4, 5, 5, 5, 5, 5]


async def test_total_limit_and_foreign_fork_point(service):
    request = await design(service, 100)
    for i in range(11):
        case = copy.deepcopy(request["cases"][0])
        case["id"] = f"extra{i}"
        request["cases"].append(case)
    with pytest.raises(ValueError, match="2000"):
        ForkExperimentSpec.model_validate(request)
    request = await design(service, 1)
    request["cases"][1]["sourceEventId"] = "A:e0"
    preview = await service.dispatch("forkExperiments.preview", request)
    assert sum(c["supported"] for c in preview["cells"]) == 2
