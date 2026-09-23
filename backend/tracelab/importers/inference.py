"""Bounded structural inference. No LLM calls or source execution."""

import io
import json
import re
from itertools import islice

import ijson

from tracelab.importers.common import prefix
from tracelab.sources.cache import key

EVENT_KEYS = {
    "messages",
    "events",
    "trajectory",
    "steps",
    "history",
    "actions",
    "observations",
    "trace",
}
FIELDS = {
    "eventId": ["id", "uuid", "event_id"],
    "trajectoryId": ["run_id", "trajectory_id", "session_id", "id"],
    "agent": ["agent_id", "worker", "agent", "agent.name"],
    "parent": ["parent_id", "parent", "parent_uuid", "parentId"],
    "type": ["event_type", "type", "kind"],
    "role": ["role", "message.role"],
    "content": ["content", "text", "message.content", "message", "observation"],
    "reasoning": ["reasoning", "reasoning_content", "reasoningContent", "thought"],
    "toolName": ["tool_name", "tool.name", "action.tool", "tool", "name"],
    "toolArguments": ["arguments", "tool.arguments", "action.arguments", "input"],
    "toolResult": ["result", "tool.result", "output"],
    "toolCalls": ["tool_calls", "toolCalls"],
    "timestamp": ["timestamp", "created_at", "time"],
    "score": ["score", "scores", "reward"],
    "metadata": ["metadata", "extra"],
    "artifacts": ["artifacts", "attachments"],
}


def get_path(value, path):
    if not path:
        return None
    if path == "$":
        return value
    if not re.fullmatch(r"\$(?:\.[A-Za-z_][\w-]*|\[\*\])*", path):
        raise ValueError(
            f"Unsupported mapping path: {path}. Use simple $.field paths and [*] arrays."
        )
    for part in path.removeprefix("$.").replace("[*]", "").split("."):
        if not part or part == "$":
            continue
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def schema(value, depth=0):
    if depth >= 8:
        return "nested"
    if isinstance(value, dict):
        return {k: schema(v, depth + 1) for k, v in sorted(value.items())}
    if isinstance(value, list):
        shapes = {json.dumps(schema(v, depth + 1), sort_keys=True) for v in value[:8]}
        return [json.loads(v) for v in sorted(shapes)]
    return (
        "null"
        if value is None
        else "boolean"
        if isinstance(value, bool)
        else "number"
        if isinstance(value, (int, float))
        else "string"
    )


def safe_preview(value, depth=0):
    if depth > 5:
        return "…"
    if isinstance(value, dict):
        return {k: safe_preview(v, depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [safe_preview(v, depth + 1) for v in value[:3]]
    return value[:240] if isinstance(value, str) else value


def infer(source, ref):
    raw = prefix(source, ref)
    sample, rows, mode, events = {}, [], "json", "$[*]"
    try:
        sample = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        for line in raw.splitlines()[:16]:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except (json.JSONDecodeError, UnicodeDecodeError):
                break
        if rows:
            mode, sample = "jsonl", rows[0]
        else:
            # Read only the existing prefix, never the rest of a large file for inference.
            try:
                for p, event, value in ijson.parse(io.BytesIO(raw), use_float=True):
                    if event == "start_array" and p.split(".")[-1] in EVENT_KEYS:
                        events = "$." + p + "[*]"
                        break
                    if p and "." not in p and event in ("string", "number", "boolean", "null"):
                        sample[p] = value
            except ijson.JSONError:
                pass
    if isinstance(sample, dict):

        def find_arrays(obj, path="$"):
            for name, value in obj.items():
                if name in EVENT_KEYS and isinstance(value, list):
                    return f"{path}.{name}[*]", value
                if isinstance(value, dict):
                    result = find_arrays(value, f"{path}.{name}")
                    if result:
                        return result

        found = find_arrays(sample)
        if found:
            events, rows = found
        elif mode == "jsonl":
            events = "$"
        elif any(name in sample for name in ("role", "content", "event_type", "tool_calls")):
            events, rows = "$", [sample]
    elif isinstance(sample, list):
        rows = sample[:8]
    if not rows and events != "$":
        selector = events.removeprefix("$.").removeprefix("$").replace("[*]", ".item").lstrip(".")
        try:
            for item in islice(ijson.items(io.BytesIO(raw), selector, use_float=True), 8):
                rows.append(item)
        except ijson.JSONError:
            pass
    row = next((r for r in rows if isinstance(r, dict)), {})
    mapping = {"events": events}
    for field, candidates in FIELDS.items():
        obj = sample if field == "trajectoryId" and isinstance(sample, dict) else row
        mapping[field] = next(
            ("$." + name for name in candidates if get_path(obj, "$." + name) is not None), ""
        )
    has_signal = bool(
        mapping["role"] or mapping["content"] or mapping["type"] or mapping["toolName"]
    )
    structural = {
        "mode": mode,
        "root": schema(sample if mode == "json" else {}),
        "events": schema(rows[:8]),
        "path": events,
    }
    # Root event counts and values never participate in the schema key.
    fingerprint = key(structural)
    return {
        "mapping": mapping,
        "mode": mode,
        "confidence": 0.88 if has_signal and rows else 0.35,
        "fingerprint": fingerprint,
        "schema": structural,
        "sample": safe_preview(
            {"header": sample if isinstance(sample, dict) else {}, "events": rows[:3]}
        ),
    }


def validate_mapping(mapping):
    allowed = {"events", *FIELDS}
    if set(mapping) - allowed:
        raise ValueError("Unknown mapping fields")
    if not mapping.get("events"):
        raise ValueError("An event-list path is required")
    for path in mapping.values():
        if path:
            get_path({}, path)
    if not any(mapping.get(k) for k in ("content", "role", "type", "toolName")):
        raise ValueError("Map at least one content, role, event type, or tool field")
    return mapping
