from tracelab.importers.base import RunReference
from tracelab.importers.bundles import propose_bundle
from tracelab.importers.profiles import approve
from tracelab.importers.registry import choose
from tracelab.ingestion.universal import capabilities, stream_trajectory
from tracelab.inspect_adapter.backend import stable_id
from tracelab.models.domain import Experiment, SourceRef, Trajectory
from tracelab.sources.cache import key, source_key
from tracelab.sources.concurrency import blocking


async def import_bundle(service, job, workspace_id, ref, mappings):
    ref = SourceRef.model_validate(ref)
    bundle = await blocking(propose_bundle, service.sources, ref)
    if not bundle["streams"]:
        raise ValueError("No agent streams found in this proposed run")
    for entry in bundle["streams"]:
        source = SourceRef.model_validate(entry["ref"])
        importer, _ = await blocking(choose, service.sources, source)
        profile = (
            await blocking(approve, service.db, service.sources, source, mappings.get(source.uri))
            if importer.name == "generic"
            else None
        )
        runs = await blocking(importer.discover_runs, service.sources, source)
        if len(runs) != 1:
            raise ValueError(
                "A bundle agent file must contain one stream; open collections separately"
            )
        run = runs[0]
        if profile:
            run.locator.update(
                mapping=profile["mapping"], mode=profile["mode"], fingerprint=profile["fingerprint"]
            )
        entry["run"] = run.wire()
    fingerprint = key(
        [
            source_key(SourceRef.model_validate(e["ref"]))
            for category in ("streams", "scores", "configs", "artifacts")
            for e in bundle[category]
        ]
    )
    eid = stable_id("exp", workspace_id, ref.uri, fingerprint)
    name = ref.metadata.get("path") or ref.uri.rstrip("/").rsplit("/", 1)[-1]
    experiment = Experiment(
        id=eid,
        workspace_id=workspace_id,
        name=name,
        source_type="generic",
        source_path=ref.uri,
        source_ref=ref,
        metadata={"format": "generic", "sourceFingerprint": fingerprint, "bundle": bundle},
    )
    service.db.put("experiments", experiment)
    run = RunReference(source=ref, format="generic", id=name, locator={"bundle": bundle})
    t = Trajectory(
        id=stable_id("traj", eid, name),
        experiment_id=eid,
        sample_id=name,
        source_ref=ref,
        capabilities=capabilities("generic", multi_agent=True, artifacts=bool(bundle["artifacts"])),
        metadata={
            "importFormat": "generic",
            "runReference": run.wire(),
            "indexState": "METADATA_READY",
            "indexJobId": job.id,
        },
    )
    if not service.db.maybe("trajectories", t.id):
        service.db.put("trajectories", t)
        await stream_trajectory(service, job, t.id)
    workspace = service.db.get("workspaces", workspace_id)
    if ref.uri not in workspace["sources"]:
        workspace["sources"].append(ref.uri)
        service.db.put("workspaces", workspace)
