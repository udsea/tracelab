import asyncio

from tracelab.models.domain import Experiment, Trajectory, Workspace


async def import_logs(service, job, workspace_id, path):
    workspace = Workspace.model_validate(service.db.get("workspaces", workspace_id))
    paths = await asyncio.to_thread(service.adapter.discover, path)
    job.total = len(paths)
    if not paths:
        raise ValueError("No Inspect logs found at this location")
    for source in paths:
        experiment = await asyncio.to_thread(service.adapter.load_experiment, source, workspace_id)
        experiment.source_ref = (await asyncio.to_thread(service.sources.resolve, source)).ref
        previous = service.db.maybe("experiments", experiment.id)
        if (
            previous
            and previous["metadata"].get("sourceFingerprint")
            != experiment.metadata["sourceFingerprint"]
        ):
            # Version a changed source instead of invalidating already-derived evidence silently.
            from tracelab.inspect_adapter.backend import stable_id

            experiment.id = stable_id(
                "exp", experiment.id, experiment.metadata["sourceFingerprint"]
            )
            experiment.name += " · updated log"
        service.db.put("experiments", experiment)
        trajectories = await asyncio.to_thread(service.adapter.list_trajectories, experiment)
        for trajectory in trajectories:
            trajectory.source_ref = experiment.source_ref
            if not service.db.maybe("trajectories", trajectory.id):
                service.db.put("trajectories", trajectory)
        job.completed += 1
        service.jobs.save(job, f"Indexed {experiment.name}: {len(trajectories)} samples")
        await asyncio.sleep(0)
    if path not in workspace.sources:
        workspace.sources.append(path)
    service.db.put("workspaces", workspace)


async def ensure_loaded(service, trajectory_id):
    lock = service.load_locks.setdefault(trajectory_id, asyncio.Lock())
    async with lock:
        trajectory = Trajectory.model_validate(service.db.get("trajectories", trajectory_id))
        if not trajectory.loaded:
            experiment = Experiment.model_validate(
                service.db.get("experiments", trajectory.experiment_id)
            )
            if trajectory.metadata.get("importFormat"):
                from tracelab.ingestion.universal import load_imported

                return await load_imported(service, trajectory, experiment)
            if (
                service.adapter.fingerprint(experiment.source_path)
                != experiment.metadata["sourceFingerprint"]
            ):
                raise ValueError(
                    "Source log changed since indexing. Re-import it to preserve a distinct provenance version."
                )
            trajectory, events, sources = await asyncio.to_thread(
                service.adapter.load_trajectory, trajectory, experiment
            )
            await asyncio.to_thread(service.db.put_many, "source_records", sources)
            await asyncio.to_thread(service.db.put_many, "events", events)
            for event in events:
                if event.type == "checkpoint":
                    service.db.put(
                        "checkpoints",
                        {
                            "id": event.id,
                            "trajectoryId": trajectory.id,
                            "eventId": event.id,
                            "index": event.index,
                            "restorable": False,
                            "metadata": event.metadata,
                        },
                    )
            service.db.put("trajectories", trajectory)
        return trajectory
