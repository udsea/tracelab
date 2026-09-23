import json
from datetime import datetime, timezone

import ijson

from tracelab.importers.base import ImportMetadata, NormalizedTrajectory, RunReference
from tracelab.models.domain import Trajectory, TrajectoryEvent
from tracelab.sources.cache import key


def text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            text(v.get("text", v.get("content", v))) if isinstance(v, dict) else text(v)
            for v in value
        )
    return json.dumps(value, ensure_ascii=False, default=str)


def timestamp(value):
    if value is None:
        return None
    if isinstance(value, (float, int)):
        divisor = 1e9 if value > 1e17 else 1e6 if value > 1e14 else 1e3 if value > 1e11 else 1
        return datetime.fromtimestamp(value / divisor, tz=timezone.utc).isoformat()
    return str(value)


def prefix(source, ref):
    return source.read_range(ref, 0, min(ref.size_bytes or 65536, 65536))


def first_record(source, ref):
    raw = prefix(source, ref).decode("utf-8-sig", errors="replace")
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            break
    try:
        value = json.JSONDecoder().raw_decode(raw.lstrip())[0]
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        # A bounded prefix may end inside an array. Read scalar header keys only.
        import io

        result = {}
        try:
            for name, event, value in ijson.parse(io.BytesIO(raw.encode()), use_float=True):
                if "." not in name and name and event in ("string", "number", "boolean", "null"):
                    result[name] = value
                if (
                    name in ("steps", "events", "messages", "resourceSpans", "resource_spans")
                    and event == "start_array"
                ):
                    result[name] = []
        except (ijson.JSONError, ValueError):
            pass
        return result


def json_lines(source, ref):
    with source.open(ref) as stream:
        line_number = 0
        while line := stream.readline(32 * 1024**2 + 1):
            line_number += 1
            if len(line) > 32 * 1024**2:
                raise ValueError(f"JSONL line {line_number} exceeds the 32 MiB record limit")
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(f"Invalid JSON at line {line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_number} must be a JSON object")
            yield line_number, value


def json_items(source, ref, path):
    with source.open(ref) as stream:
        yield from ijson.items(stream, path, use_float=True)


class EventBuilder:
    def __init__(self, trajectory_id):
        self.id, self.index = trajectory_id, 0
        self.calls = {}

    def event_id(self, external):
        return f"{self.id}:node:{key(str(external))[:20]}"

    def emit(
        self,
        kind,
        content=None,
        *,
        external=None,
        parents=None,
        role=None,
        tool=None,
        stamp=None,
        raw=None,
        agent=None,
        **metadata,
    ):
        event = TrajectoryEvent(
            id=self.event_id(external) if external is not None else f"{self.id}:e{self.index}",
            trajectory_id=self.id,
            index=self.index,
            type=kind,
            content=text(content),
            role=role,
            parent_event_ids=parents or [],
            timestamp=timestamp(stamp),
            tool=tool,
            metadata={"raw": raw, "agentId": agent, **metadata},
        )
        self.index += 1
        return event

    def message(self, msg, *, raw=None, external=None, parents=None, agent=None):
        role = msg.get("role", "assistant")
        stamp = msg.get("timestamp")
        metadata = {
            "agent": agent,
            "raw": raw or msg,
            "parents": parents,
            "stamp": stamp,
            "model": msg.get("model"),
        }
        reasoning = (
            msg.get("reasoningContent") or msg.get("reasoning_content") or msg.get("reasoning")
        )
        if reasoning:
            yield self.emit(
                "reasoning",
                reasoning,
                role="assistant",
                external=external if not msg.get("content") else None,
                **metadata,
            )
            if not msg.get("content"):
                external = None
        calls = msg.get("toolCalls") or msg.get("tool_calls") or []
        if role == "tool":
            cid = msg.get("toolCallId") or msg.get("tool_call_id")
            parent = self.calls.get(cid)
            yield self.emit(
                "tool_result",
                msg.get("content"),
                external=external,
                role=role,
                tool={
                    "name": msg.get("name")
                    or msg.get("function")
                    or (parent[1] if parent else "tool"),
                    "callId": cid,
                    "result": msg.get("content"),
                    "error": text(msg.get("error")) or None,
                },
                **(metadata | {"parents": [parent[0]] if parent else parents}),
            )
            return
        content = msg.get("content")
        if content or not (calls or reasoning):
            yield self.emit(
                role if role in ("system", "user", "assistant") else "other",
                content,
                external=external,
                role=role,
                **metadata,
            )
            external = None
        for call in calls:
            function = call.get("function", {})
            function = (
                {"name": function, "arguments": call.get("arguments")}
                if isinstance(function, str)
                else function
            )
            cid = call.get("id") or call.get("tool_call_id")
            name = function.get("name", call.get("name", "tool"))
            arguments = function.get("arguments", call.get("arguments"))
            event = self.emit(
                "tool_call",
                arguments,
                external=external,
                role="assistant",
                tool={"name": name, "callId": cid, "arguments": arguments},
                **metadata,
            )
            external = None
            if cid:
                self.calls[cid] = (event.id, name)
            yield event


class StreamImporter:
    def inspect_metadata(self, source, ref):
        header = first_record(source, ref)
        return ImportMetadata(
            name=str(
                header.get("name")
                or header.get("session_id")
                or header.get("id")
                or source.stat(ref).name
            ),
            format=self.name,
            metadata={"header": header},
        )

    def discover_runs(self, source, ref):
        meta = self.inspect_metadata(source, ref)
        return [RunReference(source=ref, format=self.name, id=meta.name, metadata=meta.metadata)]

    def load_trajectory(self, source, run):
        trajectory = Trajectory(
            id="traj_" + key(run.wire())[:20],
            experiment_id=run.locator.get("experimentId", ""),
            sample_id=run.id,
            source_ref=run.source,
        )
        events = list(self.iter_events(source, run, trajectory.id))
        trajectory.event_count, trajectory.loaded = len(events), True
        return NormalizedTrajectory(trajectory=trajectory, events=events)
