"""Deterministic, bounded semantic previews; never replace original events."""

import hashlib
import json
import math
from datetime import datetime

from tracelab.analysis.models import SemanticEvent
from tracelab.presentation import classify, visible_event


def compact(value, limit=600):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit] + (" … [truncated]" if len(text) > limit else "")


def timestamp_ms(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.timestamp() * 1000 if stamp.tzinfo else None
    except (ValueError, OverflowError):
        return None


def semantic_events(events):
    result = []
    by_id = {e["id"]: e for e in events}
    structural_ids = {
        e.get("metadata", {}).get("spanId")
        for e in events
        if e.get("metadata", {}).get("structuralKind") == "span"
    }
    seen_calls = set()
    for original in events:
        e = visible_event(original)
        meta, tool = e.get("metadata") or {}, e.get("tool") or {}
        raw = (original.get("metadata") or {}).get("raw") or {}
        if not isinstance(raw, dict):
            raw = {}
        outcome = tool.get("result")
        exit_code = (
            outcome.get("exit_code", outcome.get("returncode"))
            if isinstance(outcome, dict)
            else None
        )
        error = tool.get("error") or (e.get("content") if e["type"] == "error" else None)
        duration = meta.get("durationMs", raw.get("duration_ms"))
        if not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration < 0:
            duration = None
        agent = meta.get("agentId") or meta.get("agent")
        if isinstance(agent, dict):
            agent = agent.get("id") or agent.get("name")
        # A structural span ID is not an agent identity. Old normalized OTLP
        # records may retain such a fallback; use only recorded identity attributes.
        if meta.get("structuralKind") == "span":
            attributes = meta.get("attributes") or {}
            agent = attributes.get("gen_ai.agent.id") or attributes.get("gen_ai.agent.name")
        elif agent in structural_ids:
            # Child span events inherit only explicit recorded ownership, never span IDs.
            owners = []
            for pid in e.get("parentEventIds", []):
                attrs = by_id.get(pid, {}).get("metadata", {}).get("attributes", {})
                owner = attrs.get("gen_ai.agent.id") or attrs.get("gen_ai.agent.name")
                if owner:
                    owners.append(owner)
            agent = owners[0] if len(set(owners)) == 1 else None
        artifacts = meta.get("artifacts") or []
        effects = meta.get("environmentEffects") or []
        presentation = classify(e)
        call_id = meta.get("modelCallId")
        boundary = bool(call_id and call_id not in seen_calls)
        if call_id:
            seen_calls.add(call_id)
        result.append(
            SemanticEvent(
                event_id=e["id"],
                index=e["index"],
                agent_id=str(agent) if agent else None,
                type=e["type"],
                summary=""
                if presentation == "runtime"
                else (
                    f"[{meta.get('reasoningVisibility', 'opaque')} reasoning unavailable]"
                    if presentation == "opaque"
                    else compact(e.get("content") or "", 1200)
                ),
                presentation_class=presentation,
                reasoning_visibility=meta.get("reasoningVisibility"),
                model_call_id=call_id,
                tool_name=tool.get("name"),
                tool_arguments_summary=compact(tool["arguments"]) if "arguments" in tool else None,
                tool_result_summary=compact(outcome) if outcome is not None else None,
                tool_success=False if error else exit_code == 0 if exit_code is not None else None,
                error=compact(error) if error else None,
                timestamp=e.get("timestamp"),
                duration_ms=duration,
                parent_ids=e.get("parentEventIds", []),
                artifacts=artifacts if isinstance(artifacts, list) else [artifacts],
                environment_effects=effects if isinstance(effects, list) else [effects],
                model_call=boundary
                if call_id
                else meta.get("spanKind") == "llm"
                or meta.get("inspectEventType") == "model"
                or meta.get("modelCall") is True
                or (
                    e["type"] in ("assistant", "reasoning", "tool_call")
                    and (e.get("tokenUsage") or {}).get("output") is not None
                ),
                metadata={
                    "toolArgumentsHash": hashlib.sha256(
                        json.dumps(tool.get("arguments"), sort_keys=True, default=str).encode()
                    ).hexdigest(),
                    "tokenUsage": e.get("tokenUsage"),
                    "structuralKind": meta.get("structuralKind"),
                    "recipientAgentId": meta.get("recipientAgentId", raw.get("recipientAgentId")),
                    "relationshipType": meta.get("relationshipType", raw.get("relationshipType")),
                },
            )
        )
    return result


def coordinates(events):
    stamps = [timestamp_ms(e.timestamp) for e in events]
    origin = min((s for s in stamps if s is not None), default=None)
    explicit = any(e.model_call for e in events)
    call = 0
    points = []
    for e, stamp in zip(events, stamps, strict=True):
        boundary = (
            e.model_call
            if explicit
            else e.type == "assistant" and e.presentation_class == "semantic"
        )
        if boundary:
            call += 1
        points.append(
            {
                "id": e.event_id,
                "index": e.index,
                "elapsedMs": stamp - origin if stamp is not None else None,
                "modelCall": call,
                "modelCallBoundary": boundary,
                "agent": e.agent_id,
                "type": e.type,
                "presentationClass": e.presentation_class,
                "reasoningVisibility": e.reasoning_visibility,
                "modelCallId": e.model_call_id,
                "tool": e.tool_name,
                "error": bool(e.error) or e.tool_success is False,
                "artifacts": bool(e.artifacts),
                "durationMs": e.duration_ms,
            }
        )
    return {
        "points": points,
        "timeOriginMs": origin,
        "missingTimestamps": sum(s is None for s in stamps),
        "modelCallFidelity": "recorded"
        if explicit
        else "assistant-message proxy; generation boundaries unavailable",
    }
