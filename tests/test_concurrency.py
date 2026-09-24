"""Read scheduling and DuckDB execution contexts, without provider/network calls."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from tracelab.api import routes_trajectory
from tracelab.models.domain import Job, Trajectory
from tracelab.storage.database import Database


def test_duckdb_read_does_not_hold_other_reads_or_writer(tmp_path):
    db = Database(tmp_path / "reads.duckdb")
    entered, release = threading.Event(), threading.Event()

    def blocked(value: int) -> int:
        entered.set()
        if not release.wait(5):
            raise RuntimeError("Test failed to release blocked read")
        return value

    db.conn.create_function("blocked_read", blocked)
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            slow = pool.submit(db.read, "SELECT blocked_read(1)")
            try:
                assert entered.wait(2)
                assert pool.submit(db.read, "SELECT 42").result(timeout=1) == [(42,)]
                item = {"id": "job", "status": "running"}
                assert pool.submit(db.put, "jobs", item).result(timeout=1) == item
                assert pool.submit(db.get, "jobs", "job").result(timeout=1) == item
                assert not slow.done()
            finally:
                release.set()
            assert slow.result(timeout=2) == [(1,)]
    finally:
        db.close()


@pytest.mark.parametrize(
    "method,function,params",
    [
        ("search", "search", {"workspaceId": "ws", "query": "text"}),
        ("events.list", "event_page", {"trajectoryId": "t"}),
        ("events.locate", "event_location", {"trajectoryId": "t", "eventIndex": 70}),
        ("trajectories.list", "list_trajectories", {}),
    ],
)
async def test_slow_read_route_does_not_block_health_or_job_polling(
    service, monkeypatch, method, function, params
):
    entered, release = threading.Event(), threading.Event()
    service.db.put(
        "trajectories", Trajectory(id="t", experiment_id="exp", sample_id="s", loaded=True)
    )
    job = Job(kind="classifier", name="Still running", status="running")
    service.db.put("jobs", job)

    def blocked(*args, **kwargs):
        entered.set()
        if not release.wait(3):
            raise RuntimeError("Read handler blocked the event loop")
        return {"items": [], "total": 0}

    monkeypatch.setattr(routes_trajectory, function, blocked)
    slow = asyncio.create_task(service.dispatch(method, params))
    try:
        # The worker must enter while the event loop is free to service other RPCs.
        assert await asyncio.to_thread(entered.wait, 1)
        assert not slow.done()
        assert (await asyncio.wait_for(service.dispatch("health", {}), 0.5))["version"]
        jobs = await asyncio.wait_for(service.dispatch("jobs.list", {}), 0.5)
        assert jobs[0]["status"] == "running"
        assert not slow.done()
    finally:
        release.set()
        await slow


def test_write_transaction_rollback_and_committed_visibility(tmp_path):
    db = Database(tmp_path / "transaction.duckdb")
    try:
        db.put("jobs", {"id": "one", "status": "running"})
        with db.lock:
            db.conn.execute("BEGIN")
            db.conn.execute("DELETE FROM jobs")
            # Independent readers see the last committed snapshot, not dirty data.
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(db.get, "jobs", "one").result(timeout=1)["status"] == "running"
            db.conn.execute("ROLLBACK")
        assert db.get("jobs", "one")["status"] == "running"
        db.put_many("jobs", [{"id": "two", "status": "complete"}])
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(db.get, "jobs", "two").result(timeout=1)["status"] == "complete"
    finally:
        db.close()


async def test_first_projection_allows_job_progress_and_retries_changed_snapshot(
    service, event_factory, monkeypatch
):
    from tracelab.presentation import storage

    service.db.put(
        "trajectories",
        Trajectory(id="t", experiment_id="exp", sample_id="s", loaded=True, event_count=1),
    )
    service.db.put("events", event_factory())
    service.db.put(
        "trajectories",
        Trajectory(
            id="cached", experiment_id="exp", sample_id="cached", loaded=True, event_count=1
        ),
    )
    service.db.put("events", event_factory(tid="cached"))
    await service.dispatch("events.list", {"trajectoryId": "cached"})
    original = storage.prepared_events
    entered, release = threading.Event(), threading.Event()
    attempts = []

    def slow_projection(db, tid):
        events = original(db, tid)
        attempts.append(1)
        if len(attempts) == 1:
            entered.set()
            assert release.wait(3)
        return events

    monkeypatch.setattr(storage, "prepared_events", slow_projection)
    request = asyncio.create_task(service.dispatch("events.list", {"trajectoryId": "t"}))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        job = Job(kind="classifier", name="Progress", status="running", completed=1)
        await asyncio.wait_for(asyncio.to_thread(service.jobs.save, job), 0.5)
        assert (await service.dispatch("jobs.list", {}))[0]["completed"] == 1
        assert (
            await asyncio.wait_for(service.dispatch("events.list", {"trajectoryId": "cached"}), 0.5)
        )["total"] == 1
        # Do not let an old derived snapshot overwrite a concurrent canonical change.
        await asyncio.wait_for(
            asyncio.to_thread(service.db.put, "events", event_factory(content="new snapshot")), 0.5
        )
    finally:
        release.set()
    page = await request
    assert len(attempts) == 2
    assert page["items"][0]["preview"] == "new snapshot"
