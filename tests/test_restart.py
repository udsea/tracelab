from tracelab.api.service import Service
from tracelab.models.domain import Fork, Job, Trajectory


async def test_populated_workspace_reopens_and_recovers_only_interrupted_execution(tmp_path):
    directory = tmp_path / "workspace"
    first = Service(directory)
    parent = Trajectory(id="parent", experiment_id="exp", sample_id="original", status="unknown")
    fork = Fork(source_trajectory_id=parent.id, source_event_id="parent:e0", status="running")
    child = Trajectory(
        id="child",
        experiment_id="exp",
        sample_id="branch",
        status="running",
        parent_trajectory_id=parent.id,
        fork_id=fork.id,
    )
    job = Job(kind="classifier", name="Interrupted classifier", status="running")
    first.db.put_many("trajectories", [parent, child])
    first.db.put("forks", fork)
    first.db.put("jobs", job)
    await first.close()

    reopened = Service(directory)
    try:
        assert reopened.db.get("trajectories", parent.id) == parent.wire()
        assert reopened.db.get("trajectories", child.id)["status"] == "error"
        assert reopened.db.get("forks", fork.id)["status"] == "failed"
        assert reopened.db.get("jobs", job.id)["status"] == "failed"
        assert reopened.db.get("classifier_runs", job.id)["status"] == "failed"
    finally:
        await reopened.close()
