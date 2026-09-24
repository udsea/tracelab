"""Conservative presentation semantics shared by old records and new imports.

A signature alongside readable reasoning does not make that reasoning opaque.
No base64 heuristic is used: explicit visibility/redaction fields take precedence.
"""

VERSION = "presentation-2"
RUNTIME_TYPES = {
    "span_begin",
    "span_end",
    "sample_init",
    "sample_limit",
    "logger",
    "info",
    "approval",
    "step",
}
RAW_KEYS = {"raw", "nativeMessage", "contentBlock", "signature", "reasoning", "internal"}


def reasoning(event):
    meta = event.get("metadata") or {}
    if meta.get("intervened"):
        # An explicitly replaced branch event is new text; its preserved source
        # block is provenance, not the current content (replay follows this too).
        return "plaintext", event.get("content") or ""
    block = meta.get("contentBlock") or {}
    raw = meta.get("raw") or {}
    if (
        not block
        and isinstance(raw, dict)
        and raw.get("type")
        in (
            "reasoning",
            "thinking",
            "redacted_thinking",
            "reasoning.encrypted",
        )
    ):
        block = raw
    if not isinstance(block, dict):
        block = {}
    visibility = meta.get("reasoningVisibility", block.get("visibility"))
    text = block.get("reasoning", block.get("thinking", event.get("content")))
    summary = block.get("summary")
    hidden = block.get("redacted") is True or block.get("type") == "redacted_thinking"
    encrypted = block.get("encrypted") is True or block.get("type") == "reasoning.encrypted"
    if hidden or encrypted or visibility in ("encrypted", "redacted", "opaque"):
        if isinstance(summary, str) and summary.strip():
            return "summary", summary
        return ("encrypted" if encrypted else "redacted" if hidden else visibility), None
    if visibility == "summary":
        return "summary", summary or event.get("content") or ""
    if not text and isinstance(summary, str) and summary.strip():
        return "summary", summary
    if not text and (block.get("signature") or block.get("internal")):
        return "opaque", None
    return "plaintext", text or ""


def classify(event):
    meta = event.get("metadata") or {}
    if event["type"] == "reasoning":
        visibility, _ = reasoning(event)
        return "opaque" if visibility in ("encrypted", "redacted", "opaque") else "semantic"
    if meta.get("presentationClass") in ("semantic", "runtime", "opaque"):
        return meta["presentationClass"]
    native = meta.get("inspectType")
    if native in RUNTIME_TYPES:
        return "runtime"
    if native in ("sandbox", "state", "store"):
        # Older normalized placeholders alone do not establish environment effects.
        if not meta.get("environmentEffects") and event.get("content") in (None, "", native):
            return "runtime"
    if event["type"] == "other":
        return (
            "semantic"
            if meta.get("relationshipType") in ("delegation", "message_transfer")
            else "runtime"
        )
    if event["type"] == "assistant" and not event.get("content") and not event.get("tool"):
        return "runtime"
    return "semantic"


def prepare_event(event, source=None):
    """Annotate a copy, using recorded source structure where available. Replay metadata stays intact."""
    meta = dict(event.get("metadata") or {})
    result = {**event, "metadata": meta}
    raw = source or {}
    native = meta.get("inspectType")
    if native == "sandbox" and raw.get("action") in ("exec", "read_file", "write_file"):
        action = raw["action"]
        detail = raw.get("cmd") if action == "exec" else raw.get("file")
        if detail:
            result["content"] = f"{action}: {detail}"
            meta["environmentEffects"] = [
                {"action": action, "command" if action == "exec" else "path": detail}
            ]
            meta["presentationClass"] = "semantic"
            meta["inspectAction"] = action
    if native in ("state", "store") and raw.get("changes"):
        # Inspect duplicates conversation/output/usage into TaskState. Those
        # control-plane updates are not new agent behavior. Tool configuration
        # and scaffold store changes are concrete observations, without inferring intent.
        paths = [c.get("path", "") for c in raw["changes"] if isinstance(c, dict)]
        meaningful = native == "store" or any(
            path.split("/")[1:2] in (["tools"], ["tool_choice"]) for path in paths
        )
        meta["presentationClass"] = "semantic" if meaningful else "runtime"
        if meaningful:
            result["content"] = (
                "Recorded scaffold store changes (inspect raw details)"
                if native == "store"
                else "Tool configuration changed (inspect raw details)"
            )
    if event["type"] == "reasoning":
        visibility, content = reasoning(event)
        meta["reasoningVisibility"] = visibility
        result["content"] = content
    meta["presentationClass"] = classify(result)
    meta["presentationVersion"] = VERSION
    return result


def visible_event(event):
    """Payload-safe UI/analysis projection. Raw inspection and context replay use originals."""
    event = prepare_event(event)
    meta = {k: v for k, v in event["metadata"].items() if k not in RAW_KEYS}
    return {**event, "metadata": meta}


def research_events(events, include_runtime=False):
    projected = [visible_event(e) for e in events]
    return [e for e in projected if include_runtime or classify(e) != "runtime"]
