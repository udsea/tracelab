from tracelab.importers.base import DetectionResult, RunReference
from tracelab.importers.common import (
    EventBuilder,
    StreamImporter,
    first_record,
    json_items,
    json_lines,
    text,
)
from tracelab.importers.inference import get_path, infer


class GenericStructuredImporter(StreamImporter):
    name = "generic"

    def detect(self, source, ref):
        proposal = infer(source, ref)
        valid = proposal["confidence"] >= 0.5
        return DetectionResult(
            format=self.name,
            confidence=0.55 if valid else 0.1,
            reason="Structural field mapping requires review"
            if valid
            else "Insufficient event structure; edit the mapping",
        )

    def discover_runs(self, source, ref):
        proposal = infer(source, ref)
        return [
            RunReference(
                source=ref,
                format=self.name,
                id=str(first_record(source, ref).get("run_id") or source.stat(ref).name),
                locator={
                    "mode": proposal["mode"],
                    "mapping": proposal["mapping"],
                    "fingerprint": proposal["fingerprint"],
                },
            )
        ]

    def iter_events(self, source, run, trajectory_id):
        if run.locator.get("bundle"):
            from tracelab.importers.bundles import bundle_events

            yield from bundle_events(source, run, trajectory_id)
            return
        b = EventBuilder(trajectory_id)
        mapping = run.locator["mapping"]
        path = mapping["events"]
        mode = run.locator.get("mode", "json")
        if mode == "jsonl":
            raw_rows = (row for _, row in json_lines(source, run.source))
        else:
            selector = path.removeprefix("$.").removeprefix("$").replace("[*]", ".item").lstrip(".")
            raw_rows = json_items(source, run.source, selector)
        for row in raw_rows:
            # JSONL may envelope a series within each line. Run IDs are retained as structural scopes.
            nested = get_path(row, path) if mode == "jsonl" and path not in ("$", "$[*]") else None
            rows = nested if isinstance(nested, list) else [row]
            run_id = get_path(row, mapping.get("trajectoryId"))
            scope = None
            if nested is not None:
                scope = b.emit(
                    "environment",
                    f"Run {run_id or b.index}",
                    raw={k: v for k, v in row.items() if v is not nested},
                    agent=str(run_id or b.index),
                    structuralKind="run",
                    runIdentity=run_id,
                )
                yield scope
            for item in rows:
                if not isinstance(item, dict):
                    yield b.emit("other", item, raw=item)
                    continue
                values = {
                    key: get_path(item, value)
                    for key, value in mapping.items()
                    if key not in ("events", "trajectoryId") and value
                }
                agent = text(values.get("agent")) or (str(run_id) if run_id is not None else None)
                external = values.get("eventId")
                parent = values.get("parent")
                # IDs in independent agent streams often restart at zero.
                namespace = f"{run_id or ''}:{agent or ''}:"
                parents = (
                    [b.event_id(namespace + str(parent))]
                    if parent is not None
                    else [scope.id]
                    if scope
                    else []
                )
                role = values.get("role")
                kind = str(values.get("type") or role or "other").lower()
                kind = {
                    "thought": "reasoning",
                    "think": "reasoning",
                    "ai": "assistant",
                    "human": "user",
                    "tool": "tool_call",
                    "action": "tool_call",
                    "observation": "tool_result",
                    "result": "tool_result",
                    "function_call": "tool_call",
                    "function_result": "tool_result",
                }.get(kind, kind)
                valid = {
                    "system",
                    "user",
                    "assistant",
                    "reasoning",
                    "tool_call",
                    "tool_result",
                    "environment",
                    "score",
                    "error",
                    "checkpoint",
                    "annotation",
                    "other",
                }
                kind = kind if kind in valid else "other"
                if values.get("reasoning"):
                    yield b.emit(
                        "reasoning",
                        values["reasoning"],
                        parents=parents,
                        raw=item,
                        agent=agent,
                        stamp=values.get("timestamp"),
                    )
                tool = None
                if values.get("toolName") and kind in ("tool_call", "tool_result"):
                    tool = {
                        "name": text(values["toolName"]),
                        "arguments": values.get("toolArguments"),
                        "result": values.get("toolResult"),
                    }
                yield b.emit(
                    kind,
                    values.get(
                        "content",
                        values.get("toolArguments")
                        if kind == "tool_call"
                        else values.get("toolResult"),
                    ),
                    external=namespace + str(external) if external is not None else None,
                    parents=parents,
                    raw=item,
                    agent=agent,
                    role=role,
                    stamp=values.get("timestamp"),
                    tool=tool,
                    score=values.get("score"),
                    artifacts=values.get("artifacts"),
                    runIdentity=run_id,
                )
                if values.get("toolCalls"):
                    yield from b.message(
                        {"role": "assistant", "toolCalls": values["toolCalls"]},
                        raw=item,
                        parents=parents,
                        agent=agent,
                    )
