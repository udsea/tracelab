"""Inspect wire-format compatibility stays here. Unknown records are retained verbatim."""

import hashlib
import json
from collections import Counter

from tracelab.models.domain import ToolData, TrajectoryEvent


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:20]


def text_content(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            x.get("text", x.get("reasoning", "")) if isinstance(x, dict) else str(x) for x in value
        )
    return json.dumps(value, ensure_ascii=False) if value is not None else ""


def normalize_sample(trajectory_id: str, sample: dict) -> tuple[list[TrajectoryEvent], list[dict]]:
    events: list[TrajectoryEvent] = []
    sources: list[dict] = []
    seen: Counter = Counter()
    calls: dict[str, str] = {}

    def emit(
        kind,
        content=None,
        *,
        role=None,
        tool=None,
        timestamp=None,
        metadata=None,
        parents=None,
        usage=None,
    ):
        idx = len(events)
        event = TrajectoryEvent(
            id=f"{trajectory_id}:e{idx}",
            trajectory_id=trajectory_id,
            index=idx,
            type=kind,
            role=role,
            content=content,
            tool=tool,
            timestamp=timestamp,
            parent_event_ids=parents or ([events[-1].id] if events else []),
            token_usage=usage,
            metadata=metadata or {},
        )
        events.append(event)
        return event

    def message_key(msg):
        # IDs are not guaranteed; omit runtime-only fields from the fallback identity.
        return msg.get("id") or digest(
            {k: msg.get(k) for k in ("role", "content", "tool_calls", "tool_call_id")}
        )

    def emit_message(msg, source_id, timestamp=None, usage=None):
        role = msg.get("role", "assistant")
        meta = {"sourceRecordId": source_id, "nativeMessage": msg, "messageKey": message_key(msg)}
        if role == "tool":
            cid = msg.get("tool_call_id", "")
            emit(
                "tool_result",
                text_content(msg.get("content")),
                role=role,
                tool=ToolData(
                    name=msg.get("function") or calls.get(cid, "tool"),
                    call_id=cid,
                    result=msg.get("content"),
                    error=text_content(msg.get("error")) or None,
                ),
                timestamp=timestamp,
                metadata=meta,
            )
            return
        content = msg.get("content", "")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        first = True
        for block in blocks:
            if not isinstance(block, dict):
                block = {"type": "text", "text": str(block)}
            kind = "reasoning" if block.get("type") == "reasoning" else role
            if kind not in ("system", "user", "assistant", "reasoning"):
                kind = "other"
            content_text = block.get("reasoning", block.get("text"))
            if content_text or block.get("type") not in ("text", "reasoning"):
                emit(
                    kind,
                    content_text or f"[{block.get('type', 'content')}]",
                    role=role,
                    timestamp=timestamp,
                    metadata={**meta, "contentBlock": block}
                    if first
                    else {
                        "sourceRecordId": source_id,
                        "messageKey": message_key(msg),
                        "contentBlock": block,
                    },
                    usage=usage if first else None,
                )
                first = False
        for tc in msg.get("tool_calls") or []:
            cid = tc.get("id", "")
            name = tc.get("function", "tool")
            if isinstance(name, dict):
                args = name.get("arguments")
                name = name.get("name", "tool")
            else:
                args = tc.get("arguments")
            calls[cid] = name
            emit(
                "tool_call",
                text_content(args),
                role="assistant",
                tool=ToolData(name=name, call_id=cid, arguments=args),
                timestamp=timestamp,
                metadata=meta
                if first
                else {"sourceRecordId": source_id, "messageKey": message_key(msg)},
                usage=usage if first else None,
            )
            first = False
        if first:
            emit(
                role if role in ("system", "user", "assistant") else "other",
                "",
                role=role,
                timestamp=timestamp,
                metadata=meta,
                usage=usage,
            )

    transcript = sample.get("events") or []
    for pos, raw in enumerate(transcript):
        source_id = f"{trajectory_id}:raw{pos}"
        sources.append({"id": source_id, "trajectoryId": trajectory_id, "raw": raw})
        stamp = raw.get("timestamp")
        kind = raw.get("event", raw.get("type", "other"))
        before = len(events)
        if kind == "model":
            occurrence: Counter = Counter()
            for msg in raw.get("input") or []:
                if not isinstance(msg, dict):
                    continue
                key = message_key(msg)
                occurrence[key] += 1
                if occurrence[key] > seen[key]:
                    emit_message(msg, source_id, stamp)
            seen |= occurrence
            output = raw.get("output") or {}
            usage = output.get("usage") or {}
            choices = output.get("choices") or []
            # A trajectory follows the selected (first) choice. Alternatives stay in raw.
            if choices and choices[0].get("message"):
                msg = choices[0]["message"]
                emit_message(
                    msg,
                    source_id,
                    stamp,
                    {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
                )
                seen[message_key(msg)] += 1
        elif kind == "tool":
            cid = raw.get("id") or raw.get("tool_call_id") or ""
            name = raw.get("function", calls.get(cid, "tool"))
            if cid not in calls:
                emit(
                    "tool_call",
                    text_content(raw.get("arguments")),
                    role="assistant",
                    tool=ToolData(name=name, call_id=cid, arguments=raw.get("arguments")),
                    timestamp=stamp,
                    metadata={"sourceRecordId": source_id},
                )
                calls[cid] = name
            result = raw.get("result")
            emit(
                "tool_result",
                text_content(result),
                role="tool",
                tool=ToolData(
                    name=name,
                    call_id=cid,
                    arguments=raw.get("arguments"),
                    result=result,
                    error=text_content(raw.get("error")) or None,
                ),
                timestamp=stamp,
                metadata={"sourceRecordId": source_id, "toolError": raw.get("error")},
            )
            # Reconciled with model input below by tool_call_id as well as full identity.
        elif kind not in ("sample_init",):
            mapped = {
                "score": "score",
                "error": "error",
                "checkpoint": "checkpoint",
                "sandbox": "environment",
                "state": "environment",
                "store": "environment",
                "input": "user",
            }.get(kind, "other")
            emit(
                mapped,
                text_content(
                    raw.get("message", raw.get("content", raw.get("value", raw.get("error", kind))))
                ),
                timestamp=stamp,
                metadata={"sourceRecordId": source_id, "inspectType": kind},
            )
        if len(events) == before:
            # Even non-rendered source events are discoverable; nothing is silently dropped.
            emit(
                "other",
                kind,
                timestamp=stamp,
                metadata={"sourceRecordId": source_id, "inspectType": kind},
            )

    if not transcript:
        for pos, msg in enumerate(sample.get("messages") or []):
            source_id = f"{trajectory_id}:message{pos}"
            sources.append({"id": source_id, "trajectoryId": trajectory_id, "raw": msg})
            emit_message(msg, source_id)

    # Tool events and a subsequent model's tool messages refer to the same completed call.
    result_ids = set()
    deduped = []
    for event in events:
        if event.type == "tool_result" and event.tool and event.tool.call_id:
            key = event.tool.call_id
            if key in result_ids:
                continue
            result_ids.add(key)
        deduped.append(event)
    remap = {event.id: f"{trajectory_id}:e{idx}" for idx, event in enumerate(deduped)}
    for idx, event in enumerate(deduped):
        event.id = remap[event.id]
        event.index = idx
        event.parent_event_ids = [deduped[idx - 1].id] if idx else []
    sources.append(
        {
            "id": f"{trajectory_id}:sample",
            "trajectoryId": trajectory_id,
            "raw": {k: v for k, v in sample.items() if k not in ("events", "messages")},
            "messages": sample.get("messages", []),
        }
    )
    return deduped, sources
