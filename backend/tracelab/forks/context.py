import copy
import json

from tracelab.models.domain import Fork


def apply_interventions(events: list[dict], fork: Fork):
    """Interventions modify copies. The parent and its raw Inspect records never change."""
    result = copy.deepcopy(events)
    appended = []
    config = dict(fork.model_overrides)
    for intervention in fork.interventions:
        item = intervention.wire()
        kind = item["type"]
        if "eventId" in item:
            matches = [e for e in result if e["id"] == item["eventId"]]
            if not matches:
                raise ValueError("Intervention event is not in the selected prefix")
            event = matches[0]
            if event["type"] not in (
                "system",
                "user",
                "assistant",
                "reasoning",
                "tool_call",
                "tool_result",
            ):
                raise ValueError(
                    "This event is not model context and cannot be edited in a context-only fork"
                )
            if kind == "remove_event":
                result.remove(event)
            elif kind == "replace_content":
                if event["type"] == "tool_call":
                    raise ValueError(
                        "A tool call's preview is not editable model text; remove its call and result together or replace its result"
                    )
                if event["metadata"].get("contentBlock", {}).get("signature"):
                    raise ValueError(
                        "Signed reasoning cannot be edited. Remove the reasoning event or choose an unsigned text event."
                    )
                event["content"] = item["content"]
                event["metadata"]["intervened"] = True
                if event["type"] == "tool_result" and event.get("tool"):
                    event["tool"]["result"] = item["content"]
            elif kind == "replace_tool_result":
                if event["type"] != "tool_result":
                    raise ValueError("Replace tool result requires a tool_result event")
                event["tool"]["result"] = item["value"]
                event["tool"]["error"] = None
                event["content"] = (
                    item["value"] if isinstance(item["value"], str) else json.dumps(item["value"])
                )
                event["metadata"]["intervened"] = True
        elif kind == "append_message":
            appended.append({"role": item["role"], "content": item["content"]})
        elif kind == "system_prompt_override":
            result = [e for e in result if e["type"] != "system"]
            appended.insert(0, {"role": "system", "content": item["content"]})
        elif kind == "model_override":
            config["model"] = item["model"]
        elif kind == "generation_override":
            config["parameters"] = {**config.get("parameters", {}), **item["parameters"]}
    return result, appended, config


def context_messages(events: list[dict], appended: list[dict]) -> list[dict]:
    messages = []
    assistant_group = None
    pending = set()
    for event in events:
        kind = event["type"]
        if event["metadata"].get("inspectType") in ("compaction", "branch"):
            raise ValueError(
                "This prefix contains compaction or agent branching; its active model context cannot be reconstructed faithfully by this adapter."
            )
        raw_block = event["metadata"].get("contentBlock")
        if raw_block and raw_block.get("type") not in ("text", "reasoning"):
            raise ValueError(
                "This prefix contains unsupported non-text context. Its raw content is preserved, but context replay is unavailable."
            )
        if kind in ("system", "user"):
            if pending:
                raise ValueError("Choose a boundary after all pending tool results")
            messages.append({"role": kind, "content": event.get("content") or ""})
            assistant_group = None
        elif kind in ("assistant", "reasoning", "tool_call"):
            group = event["metadata"].get("messageKey", event["id"])
            if assistant_group != group:
                if pending:
                    raise ValueError(
                        "Context contains an unresolved tool call. Include its result or remove its call too."
                    )
                messages.append({"role": "assistant", "content": [], "tool_calls": []})
                assistant_group = group
            msg = messages[-1]
            if kind == "tool_call":
                tool = event["tool"]
                cid = tool.get("callId") or event["id"]
                pending.add(cid)
                msg["tool_calls"].append(
                    {
                        "id": cid,
                        "function": tool["name"],
                        "arguments": tool.get("arguments") or {},
                        "type": "function",
                    }
                )
            else:
                # Reasoning history is preserved as its own block, not invented from visible prose.
                block = (
                    {"type": "reasoning", "reasoning": event.get("content") or ""}
                    if kind == "reasoning"
                    else {"type": "text", "text": event.get("content") or ""}
                )
                if raw_block and not event["metadata"].get("intervened"):
                    block = copy.deepcopy(raw_block)
                msg["content"].append(block)
        elif kind == "tool_result":
            tool = event["tool"]
            result_blocks = tool.get("result")
            if isinstance(result_blocks, list) and any(
                isinstance(b, dict) and b.get("type") not in (None, "text") for b in result_blocks
            ):
                raise ValueError(
                    "Multimodal tool outputs are preserved but are not supported for context replay"
                )
            cid = tool.get("callId")
            if cid not in pending:
                raise ValueError(
                    "Tool result has no matching call in the edited prefix. Remove both or retain both."
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": cid,
                    "function": tool["name"],
                    "content": event.get("content") or "",
                }
            )
            if tool.get("error"):
                error = event["metadata"].get("nativeMessage", {}).get("error") or event[
                    "metadata"
                ].get("toolError")
                if not isinstance(error, dict):
                    error = {"type": "unknown", "message": tool["error"]}
                messages[-1]["error"] = copy.deepcopy(error)
            pending.remove(cid)
            assistant_group = None
    if pending:
        raise ValueError("Selected event leaves a pending tool call. Fork after its tool result.")
    systems = [m for m in appended if m["role"] == "system"]
    messages = systems + messages + [m for m in appended if m["role"] != "system"]
    if not messages:
        raise ValueError("The intervention removed all model context")
    return messages
