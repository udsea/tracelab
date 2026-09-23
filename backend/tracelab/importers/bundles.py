import json

from tracelab.importers.base import RunReference
from tracelab.importers.common import EventBuilder
from tracelab.models.domain import SourceRef
from tracelab.sources.cache import key


def propose_bundle(source, ref):
    entries = source.list(ref)
    streams, scores, configs, artifacts = [], [], [], []
    for entry in entries:
        name = entry.name.lower()
        if entry.is_directory:
            if name in ("artifacts", "outputs", "attachments"):
                artifacts.append(entry.wire())
        elif name in ("scores.json", "score.json", "result.json", "results.json"):
            scores.append(entry.wire())
        elif name.startswith(("config.", "metadata.", "settings.")):
            configs.append(entry.wire())
        elif name.endswith((".jsonl", ".ndjson", ".json")):
            streams.append(entry.wire())
    return {
        "ref": ref.wire(),
        "streams": streams,
        "scores": scores,
        "configs": configs,
        "artifacts": artifacts,
    }


def bundle_events(source, run, trajectory_id):
    from tracelab.importers.registry import get_importer

    b = EventBuilder(trajectory_id)
    bundle = run.locator["bundle"]
    root = b.emit(
        "environment",
        run.id,
        raw=bundle,
        structuralKind="workflow",
        artifacts=bundle.get("artifacts", []),
    )
    yield root
    for item in bundle["streams"]:
        child = RunReference.model_validate(item["run"])
        prefix = trajectory_id + ":stream:" + key(child.source.uri)[:12]
        scope = b.emit(
            "environment",
            item["name"],
            external=prefix,
            parents=[root.id],
            agent=item["name"],
            structuralKind="agent",
            sourceRef=child.source.wire(),
        )
        yield scope
        for event in get_importer(child.format).iter_events(source, child, prefix):
            event.trajectory_id = trajectory_id
            event.index = b.index
            b.index += 1
            if not event.parent_event_ids:
                event.parent_event_ids = [scope.id]
            event.metadata["agentId"] = (
                item["name"] + "/" + str(event.metadata.get("agentId") or "main")
            )
            event.metadata["sourceRef"] = child.source.wire()
            yield event
    for category in ("configs", "scores"):
        for entry in bundle.get(category, []):
            ref = SourceRef.model_validate(entry["ref"])
            with source.open(ref) as stream:
                raw = stream.read(1024**2 + 1)
            truncated = len(raw) > 1024**2
            value = raw[: 1024**2].decode("utf-8", errors="replace")
            if not truncated:
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            yield b.emit(
                "score" if category == "scores" else "environment",
                value,
                parents=[root.id],
                raw=value,
                sourceRef=ref.wire(),
                truncated=truncated,
                structuralKind="run_metadata",
            )
    for entry in bundle.get("artifacts", []):
        yield b.emit(
            "environment",
            entry["name"],
            parents=[root.id],
            raw=entry,
            artifacts=[entry],
            structuralKind="artifact_directory",
        )
