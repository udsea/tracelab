import asyncio

from tracelab.importers.base import RunReference
from tracelab.importers.registry import choose, get_importer
from tracelab.inspect_adapter.backend import stable_id
from tracelab.models.domain import Experiment, Job, Trajectory, TrajectoryCapabilities
from tracelab.sources.cache import source_key
from tracelab.sources.concurrency import blocking


def next_batch(iterator, size=128):
    batch = []
    try:
        for _ in range(size):
            batch.append(next(iterator))
    except StopIteration:
        return batch, None, True
    except Exception as exc:
        return batch, exc, True
    return batch, None, False


def capabilities(format, *, ready=False, multi_agent=False, artifacts=False):
    context = format == "inspect" and ready
    return TrajectoryCapabilities(
        classify=ready,
        segment=ready,
        multi_agent_graph=multi_agent,
        artifacts=artifacts,
        context_fork=context,
        reason="Context replay only; original tools and environment are not restored."
        if context
        else "Replay requires a verified context reconstruction and execution integration; readable traces alone do not provide it.",
    )


async def import_sources(service, job, workspace_id, refs, mappings=None):
    job.total = len(refs)
    errors = []
    for value in refs:
        try:
            meta = await blocking(service.sources.resolve, value)
            if meta.is_directory:
                raise ValueError("Select files within the source browser before importing")
            ref, provider = meta.ref, service.sources.provider(meta.ref)
            importer, _ = await blocking(choose, provider, ref)
            profile = None
            if importer.name == "generic":
                from tracelab.importers.profiles import approve

                profile = await blocking(
                    approve, service.db, provider, ref, (mappings or {}).get(ref.uri)
                )
            info = await blocking(importer.inspect_metadata, provider, ref)
            fingerprint = ref.etag if ref.kind == "local" else source_key(ref)
            exp_id = stable_id("exp", workspace_id, ref.uri)
            previous = service.db.maybe("experiments", exp_id)
            if previous and previous["metadata"].get("sourceFingerprint") != fingerprint:
                exp_id = stable_id("exp", exp_id, fingerprint)
            experiment = Experiment(
                id=exp_id,
                workspace_id=workspace_id,
                name=info.name,
                source_type=importer.name,
                source_path=ref.uri,
                source_ref=ref,
                metadata={
                    **info.metadata,
                    "sourceFingerprint": fingerprint,
                    "format": importer.name,
                    "indexState": "METADATA_READY",
                },
            )
            service.db.put("experiments", experiment)
            runs = await blocking(importer.discover_runs, provider, ref)
            for run in runs:
                if profile:
                    from tracelab.importers.inference import get_path

                    run.locator.update(
                        mapping=profile["mapping"],
                        mode=profile["mode"],
                        fingerprint=profile["fingerprint"],
                    )
                    run.id = str(
                        get_path(
                            info.metadata.get("header", {}), profile["mapping"].get("trajectoryId")
                        )
                        or run.id
                    )
                if importer.name == "inspect":
                    t = Trajectory.model_validate(run.metadata["trajectory"])
                    t.experiment_id = exp_id
                    t.id = stable_id("traj", exp_id, t.metadata["inspectSampleId"], t.epoch)
                    t.source_ref = ref
                    t.capabilities = capabilities("inspect")
                else:
                    t = Trajectory(
                        id=stable_id("traj", exp_id, run.id),
                        experiment_id=exp_id,
                        sample_id=run.id,
                        source_ref=ref,
                        metadata={"format": importer.name},
                    )
                    t.capabilities = capabilities(importer.name)
                t.metadata.update(
                    importFormat=importer.name, runReference=run.wire(), indexState="METADATA_READY"
                )
                if service.db.maybe("trajectories", t.id):
                    continue
                service.db.put("trajectories", t)
                if importer.name != "inspect":
                    index_job = Job(
                        kind="import", name=f"Index {info.name}", metadata={"trajectoryId": t.id}
                    )
                    t.metadata["indexJobId"] = index_job.id
                    service.db.put("trajectories", t)
                    service.jobs.start(
                        index_job, lambda j, tid=t.id: stream_trajectory(service, j, tid)
                    )
            job.completed += 1
            service.jobs.save(job, f"Metadata ready: {info.name} · {len(runs)} trajectories")
            workspace = service.db.get("workspaces", workspace_id)
            if ref.uri not in workspace["sources"]:
                workspace["sources"].append(ref.uri)
                service.db.put("workspaces", workspace)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            errors.append(str(exc))
            service.jobs.save(job, f"Import error: {exc}")
        await asyncio.sleep(0)
    if errors:
        raise ValueError("; ".join(errors))


async def stream_trajectory(service, job, trajectory_id):
    t = Trajectory.model_validate(service.db.get("trajectories", trajectory_id))
    run = RunReference.model_validate(t.metadata["runReference"])
    provider = service.sources
    importer = get_importer(run.format)
    t.metadata["indexState"] = "INDEXING"
    service.db.put("trajectories", t)
    iterator = importer.iter_events(provider, run, t.id)
    multi_agent = False
    try:
        if run.source.kind == "local" and provider.stat(run.source).ref.etag != run.source.etag:
            raise ValueError(
                "Source changed; import a new revision instead of retrying the old snapshot"
            )
        while True:
            batch, failure, finished = await blocking(next_batch, iterator)
            if not batch:
                if failure:
                    raise failure
                break
            if len({e.id for e in batch}) != len(batch):
                raise ValueError("Duplicate event identifiers in source; review its mapping/format")
            existing = dict(
                service.db.query(
                    "SELECT id,event_index FROM events WHERE id IN ("
                    + ",".join("?" for _ in batch)
                    + ")",
                    [e.id for e in batch],
                )
            )
            if any(e.id in existing and existing[e.id] != e.index for e in batch):
                raise ValueError("Source reuses an event identifier at different positions")
            # Deterministic event IDs permit safe retries; old available events remain readable.
            await blocking(service.db.put_many, "events", batch)
            t.event_count = max(t.event_count, batch[-1].index + 1)
            t.metadata["indexState"] = "PARTIALLY_AVAILABLE"
            multi_agent |= any(e.parent_event_ids or e.metadata.get("agentId") for e in batch)
            for event in batch:
                if event.type == "score" and isinstance(event.metadata.get("raw"), dict):
                    t.scores.update(event.metadata["raw"])
                if event.metadata.get("model") and not t.model:
                    t.model = event.metadata["model"]
            t.capabilities = capabilities(
                run.format,
                multi_agent=multi_agent,
                artifacts=bool(run.locator.get("bundle", {}).get("artifacts")),
            )
            service.db.put("trajectories", t)
            job.completed = t.event_count
            job.metadata.update(indexedEvents=t.event_count, sourceBytes=run.source.size_bytes)
            service.jobs.save(job)
            await asyncio.sleep(0)
            if failure:
                raise failure
            if finished:
                break
        if run.source.kind == "local" and provider.stat(run.source).ref.etag != run.source.etag:
            raise ValueError("Source changed during indexing. Import a new source version.")
        t.loaded = True
        t.metadata["indexState"] = "READY"
        t.metadata.pop("indexError", None)
        t.capabilities = capabilities(
            run.format,
            ready=True,
            multi_agent=multi_agent,
            artifacts=bool(run.locator.get("bundle", {}).get("artifacts")),
        )
        job.total = job.completed
    except BaseException as exc:
        t.metadata.update(
            indexState="ERROR",
            indexError=str(exc) or "Indexing cancelled; available events are preserved",
        )
        raise
    finally:
        iterator.close()
        service.db.put("trajectories", t)


async def load_imported(service, trajectory, experiment):
    if trajectory.metadata.get("importFormat") != "inspect":
        # Streaming jobs own writes. Reading partial events never restarts or truncates them.
        return trajectory
    ref = trajectory.source_ref
    provider = service.sources.provider(ref)
    if (
        ref.kind == "local"
        and provider.stat(ref).ref.etag != experiment.metadata["sourceFingerprint"]
    ):
        raise ValueError(
            "Source changed since indexing. Import a new revision; existing analysis is preserved."
        )
    run = RunReference.model_validate(trajectory.metadata["runReference"])
    run.metadata.update(trajectory=trajectory.wire(), experiment=experiment.wire())
    result = await blocking(get_importer("inspect").load_trajectory, provider, run)
    await blocking(service.db.put_many, "source_records", result.raw_records)
    await blocking(service.db.put_many, "events", result.events)
    t = result.trajectory
    t.metadata["indexState"] = "READY"
    t.capabilities = capabilities("inspect", ready=True)
    from tracelab.forks.context import context_messages

    try:
        context_messages([event.wire() for event in result.events], [])
    except ValueError as exc:
        t.capabilities.context_fork = False
        t.capabilities.reason = str(exc)
    service.db.put("trajectories", t)
    return t
