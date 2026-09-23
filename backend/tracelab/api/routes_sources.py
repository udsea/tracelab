import asyncio
import threading
from pathlib import PurePosixPath

from tracelab.importers.registry import detect
from tracelab.ingestion.universal import import_sources, stream_trajectory
from tracelab.models.domain import Job, SourceRef
from tracelab.sources.cache import source_key
from tracelab.sources.concurrency import blocking
from tracelab.sources.provenance import cache_stats, related_refs
from tracelab.sources.refs import hf_url, source_ref

METHODS = {
    "sources.connect",
    "sources.list",
    "sources.detect",
    "sources.add",
    "sources.info",
    "sources.pin",
    "sources.clear",
    "sources.freshness",
    "sources.retry",
    "cache.stats",
    "cache.configure",
    "cache.clear",
    "sources.assist",
    "sources.bundle",
    "sources.addBundle",
}


def hint(name):
    return {".eval": "Inspect", ".jsonl": "JSONL", ".ndjson": "JSONL", ".json": "JSON"}.get(
        PurePosixPath(name).suffix.lower()
    )


async def handle(service, method, p):
    if method == "sources.connect":
        ref = source_ref(
            p["uri"],
            kind=p.get("kind"),
            repo_type=p.get("repoType", "dataset"),
            revision=p.get("revision", "main"),
        )
        provider = service.sources.provider(ref)
        if ref.kind == "huggingface":
            ref = await asyncio.to_thread(provider.resolve, ref, True)
        meta = await asyncio.to_thread(provider.stat, ref)
        return meta.wire()
    if method == "sources.list":
        ref = SourceRef.model_validate(p["ref"])
        provider = service.sources.provider(ref)
        entries = (
            await asyncio.to_thread(provider.glob, ref, "*")
            if p.get("recursive")
            else await asyncio.to_thread(provider.list, ref)
        )
        return [{**entry.wire(), "formatHint": hint(entry.name)} for entry in entries]
    if method == "sources.detect":
        meta = await asyncio.to_thread(service.sources.resolve, p["ref"])
        provider = service.sources.provider(meta.ref)
        results = await asyncio.to_thread(detect, provider, meta.ref)
        extra = {}
        if results[0].format == "generic" or results[0].confidence < 0.5:
            from tracelab.importers.profiles import proposal

            extra = await asyncio.to_thread(proposal, service.db, provider, meta.ref)
        return {"ref": meta.ref.wire(), "detections": [r.wire() for r in results], **extra}
    if method == "sources.assist":
        from tracelab.importers.profiles import assist

        if p.get("explicitConsent") is not True:
            raise ValueError(
                "Schema assistance requires an explicit action to send the displayed preview to the configured model"
            )
        return await assist(service, SourceRef.model_validate(p["ref"]), p["provider"], p["model"])
    if method == "sources.add":
        job = Job(
            kind="import",
            name="Index trajectory sources",
            metadata={"workspaceId": p["workspaceId"]},
        )
        return service.jobs.start(
            job,
            lambda j: import_sources(service, j, p["workspaceId"], p["refs"], p.get("mappings")),
        )
    if method == "sources.bundle":
        from tracelab.importers.bundles import propose_bundle

        return await blocking(propose_bundle, service.sources, SourceRef.model_validate(p["ref"]))
    if method == "sources.addBundle":
        from tracelab.ingestion.bundles import import_bundle

        job = Job(
            kind="import", name="Index run bundle", metadata={"workspaceId": p["workspaceId"]}
        )
        return service.jobs.start(
            job,
            lambda j: import_bundle(service, j, p["workspaceId"], p["ref"], p.get("mappings", {})),
        )
    if method == "sources.retry":
        t = service.db.get("trajectories", p["trajectoryId"])
        if t["metadata"].get("indexState") != "ERROR":
            raise ValueError("Only interrupted or failed indexing can be retried")
        return service.jobs.start(
            Job(
                kind="import", name="Retry trajectory indexing", metadata={"trajectoryId": t["id"]}
            ),
            lambda j: stream_trajectory(service, j, t["id"]),
        )
    if method == "sources.info":
        t = service.db.get("trajectories", p["trajectoryId"])
        experiment = service.db.get("experiments", t["experimentId"])
        ref = SourceRef.model_validate(
            t.get("sourceRef")
            or experiment.get("sourceRef")
            or source_ref(experiment["sourcePath"]).wire()
        )
        return {
            "ref": ref.wire(),
            "format": experiment["sourceType"],
            "importedAt": experiment["importedAt"],
            "cache": cache_stats(service.sources.cache, related_refs(t, ref)),
            "indexState": t["metadata"].get(
                "indexState", "READY" if t["loaded"] else "METADATA_READY"
            ),
            "indexError": t["metadata"].get("indexError"),
            "indexedEvents": t["eventCount"],
            "capabilities": t.get("capabilities"),
            "url": hf_url(ref)
            if ref.kind == "huggingface"
            else ref.uri
            if ref.kind == "http"
            else None,
        }
    if method == "sources.pin":
        ref = SourceRef.model_validate(p["ref"])
        if ref.kind == "local":
            raise ValueError("This source is already local")
        job = Job(kind="import", name="Pin source offline", metadata={"source": ref.uri})

        async def pin(j):
            cancelled = threading.Event()

            def progress(done, total):
                if cancelled.is_set():
                    raise InterruptedError("Offline pin cancelled")
                j.completed, j.total = done, total or 0
                service.jobs.save(j)

            refs = [ref]
            if p.get("trajectoryId"):
                trajectory = service.db.get("trajectories", p["trajectoryId"])
                bundle = (
                    trajectory["metadata"].get("runReference", {}).get("locator", {}).get("bundle")
                )
                if bundle:
                    refs = [
                        SourceRef.model_validate(entry["ref"])
                        for category in ("streams", "scores", "configs")
                        for entry in bundle[category]
                    ]
                    for entry in bundle["artifacts"]:
                        directory = SourceRef.model_validate(entry["ref"])
                        entries = await blocking(service.sources.glob, directory, "*")
                        refs.extend(e.ref for e in entries if not e.is_directory)
            for selected in refs:
                if selected.kind != "local":
                    await blocking(
                        service.sources.provider(selected).pin,
                        selected,
                        progress,
                        on_cancel=cancelled.set,
                    )
            if p.get("trajectoryId"):
                trajectory = service.db.get("trajectories", p["trajectoryId"])
                trajectory["metadata"]["offlineFiles"] = [r.wire() for r in refs]
                service.db.put("trajectories", trajectory)

        return service.jobs.start(job, pin)
    if method == "sources.clear":
        ref = SourceRef.model_validate(p["ref"])
        refs = (
            related_refs(service.db.get("trajectories", p["trajectoryId"]), ref)
            if p.get("trajectoryId")
            else [ref]
        )
        for selected in refs:
            service.sources.cache.clear(source_key(selected), include_pinned=True)
        return cache_stats(service.sources.cache, refs)
    if method == "sources.freshness":
        ref = SourceRef.model_validate(p["ref"])
        if ref.kind != "huggingface":
            raise ValueError("Revision checks are available for Hugging Face repositories")
        requested = ref.model_copy(deep=True)
        requested.metadata.pop("commitSha", None)
        requested.revision = ref.metadata.get("requestedRevision", "main")
        current = await asyncio.to_thread(service.sources.provider(ref).resolve, requested, True)
        return {
            "imported": ref.revision,
            "current": current.revision,
            "changed": current.revision != ref.revision,
            "ref": current.wire(),
            "offline": current.metadata.get("offlineMetadata", False),
        }
    if method == "cache.stats":
        return service.sources.cache.stats()
    if method == "cache.configure":
        return service.sources.cache.configure(int(p["maximumBytes"]))
    if method == "cache.clear":
        return service.sources.cache.clear()
    raise ValueError("Unknown source command")
