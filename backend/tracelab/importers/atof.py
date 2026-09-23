from tracelab.importers.base import DetectionResult
from tracelab.importers.common import EventBuilder, StreamImporter, first_record, json_lines, text


def normalize_atof(row, builder):
    """Transport-independent ATOF event normalization; opaque data is never guessed into chat."""
    uuid = row.get("uuid")
    kind, phase, category = row.get("kind"), row.get("scope_category"), row.get("category")
    if not uuid or not kind:
        raise ValueError("ATOF event requires uuid and kind")
    external = f"{uuid}:{phase or kind}"
    parent = row.get("parent_uuid")
    parents = [builder.event_id(f"{parent}:start")] if parent else []
    if phase == "end":
        parents.append(builder.event_id(f"{uuid}:start"))
    profile = row.get("category_profile") or {}
    data = row.get("data")
    event_type = "other"
    tool = None
    if category == "tool" and kind == "scope":
        event_type = "tool_call" if phase == "start" else "tool_result"
        tool = {
            "name": row.get("name", "tool"),
            "callId": profile.get("tool_call_id") or uuid,
            "arguments": data if phase == "start" else None,
            "result": data if phase == "end" else None,
        }
    elif "error" in (row.get("attributes") or []):
        event_type = "error"
    elif category in ("agent", "function", "retriever", "workflow"):
        event_type = "environment"
    elif kind == "mark":
        event_type = "annotation"
    return builder.emit(
        event_type,
        row.get("name") or text(data),
        external=external,
        parents=parents,
        tool=tool,
        stamp=row.get("timestamp"),
        raw=row,
        agent=uuid if category == "agent" else parent,
        scopeId=uuid,
        scopePhase=phase,
        category=category,
        categoryProfile=profile,
        model=profile.get("model_name"),
        structuralKind="scope" if kind == "scope" else kind,
    )


class ATOFImporter(StreamImporter):
    name = "atof"

    def detect(self, source, ref):
        row = first_record(source, ref)
        match = "atof_version" in row and "uuid" in row and "kind" in row
        return DetectionResult(
            confidence=0.99 if match else 0,
            format=self.name,
            reason="ATOF version and event envelope" if match else "No ATOF envelope",
        )

    def iter_events(self, source, run, trajectory_id):
        builder = EventBuilder(trajectory_id)
        for _, row in json_lines(source, run.source):
            yield normalize_atof(row, builder)
