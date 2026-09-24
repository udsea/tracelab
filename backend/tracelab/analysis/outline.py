"""Evidence-based outline. Activities may overlap; unknown narrative intent stays unknown."""

import re
from collections import Counter

from tracelab.analysis.models import OutlineNode
from tracelab.analysis.semantic import timestamp_ms
from tracelab.models.domain import now


def statistics(events):
    times = [timestamp_ms(e.timestamp) for e in events]
    valid = [t for t in times if t is not None]
    files = set()
    for e in events:
        files.update(re.findall(r"(?:[\w.-]+/)+[\w.-]+", e.tool_arguments_summary or ""))
    return {
        "eventCount": len(events),
        "durationMs": max(valid) - min(valid) if len(valid) > 1 else None,
        "timedEvents": len(valid),
        "modelCalls": sum(e.model_call for e in events),
        "toolCalls": sum(e.type == "tool_call" for e in events),
        "tools": dict(
            Counter(e.tool_name for e in events if e.tool_name and e.type == "tool_call")
        ),
        "filesReferenced": sorted(files),
        "errors": sum(bool(e.error) or e.tool_success is False for e in events),
        "agents": sorted(
            {
                agent
                for e in events
                for agent in (e.agent_id, e.metadata.get("recipientAgentId"))
                if isinstance(agent, str)
            }
        ),
        "artifacts": [a for e in events for a in e.artifacts],
    }


def build_outline(tid, events, segments=()):
    nodes = []

    def add(kind, label, subset, id=None, parent=None, provenance=None):
        if not subset:
            return
        node = OutlineNode(
            trajectory_id=tid,
            kind=kind,
            label=label,
            start_event_index=subset[0].index,
            end_event_index=subset[-1].index,
            evidence_event_ids=[e.event_id for e in subset],
            parent_id=parent,
            stats=statistics(subset),
            provenance=provenance
            or {"algorithm": "recorded-activity-v1", "createdAt": now(), "heuristic": True},
        )
        if id:
            node.id = id
        nodes.append(node)

    for s in segments:
        add(
            "episode" if s.get("parentId") else "segment",
            s["label"],
            [e for e in events if s["startEvent"] <= e.index <= s["endEvent"]],
            s["id"],
            s.get("parentId"),
            s.get("provenance"),
        )

    # Runs of observable activity, not invented semantic phases.
    def category(e):
        text = (e.tool_name or "") + " " + (e.tool_arguments_summary or "")
        if e.error or e.tool_success is False:
            return "Errors / failed tool outcomes"
        if re.search(r"\b(pytest|npm test|pnpm test|cargo test|unittest)\b", text):
            return "Test execution"
        if re.search(r"\b(write_file|apply_patch|edit_file|str_replace)\b", text):
            return "File modification attempts"
        if e.tool_name:
            return "Tool activity"
        if e.type == "reasoning":
            return "Reasoning"
        return "Messages / recorded state"

    # Observable tool activity determines episode boundaries. Bookkeeping between
    # calls belongs to that region, without assigning an invented agent intention.
    groups = []
    active = "Opening context / recorded state"
    for e in events:
        if e.type == "tool_call":
            text = (e.tool_name or "") + " " + (e.tool_arguments_summary or "")
            active = category(e)
            if active == "Tool activity" and re.search(
                r"\b(read_file|cat|ls|find|grep|rg|head|tail)\b", text
            ):
                active = "Repository / environment inspection"
        if groups and groups[-1][0] == active:
            groups[-1][1].append(e)
        else:
            groups.append((active, [e]))
    for label, subset in groups:
        add("episode", label, subset)
    for label in ("Test execution", "File modification attempts", "Errors / failed tool outcomes"):
        subset = [e for e in events if category(e) == label]
        add("activity", label, subset)
    signatures = {}
    for e in events:
        if e.type == "tool_call":
            key = (e.agent_id, e.tool_name, e.metadata.get("toolArgumentsHash"))
            recent = [x for x in signatures.get(key, []) if e.index - x.index <= 60]
            recent.append(e)
            signatures[key] = recent
            if len(recent) == 4:
                add(
                    "episode",
                    "Repeated tool invocation",
                    [x for x in events if recent[0].index <= x.index <= e.index],
                )
    by_id = {e.event_id: e for e in events}
    for e in events:
        if (
            e.agent_id
            and e.metadata.get("recipientAgentId")
            and e.metadata.get("relationshipType") in ("message_transfer", "delegation")
        ):
            add("moment", "Recorded message transfer", [e])
            break
        if any(
            p in by_id and e.agent_id and by_id[p].agent_id and by_id[p].agent_id != e.agent_id
            for p in e.parent_ids
        ):
            add("moment", "Recorded cross-agent relationship", [e])
            break
    return sorted(nodes, key=lambda n: (n.start_event_index, n.end_event_index, n.kind))
