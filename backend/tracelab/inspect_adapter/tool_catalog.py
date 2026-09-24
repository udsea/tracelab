"""Explicit public Inspect ModelEvent.tools only. Never derive schemas from call arguments."""

import copy

from inspect_ai.model import ChatMessageTool
from inspect_ai.tool import ToolInfo

from tracelab.classifiers.runner import canonical_hash
from tracelab.forks.replay import RecordedToolCatalog, RecordedToolDefinition, ReplayUnsupported


def recorded_tool_info(name, description, parameters):
    schema = copy.deepcopy(parameters)
    # JSON Schema permits additional properties when absent. Inspect's ToolParams
    # default is false, so make the source's standard default explicit.
    schema.setdefault("additionalProperties", True)
    info = ToolInfo(name=name, description=description or "", parameters=schema)
    restored = info.model_dump(mode="json")["parameters"]

    def retained(original, parsed):
        if isinstance(original, dict):
            return isinstance(parsed, dict) and all(
                value is None or (key in parsed and retained(value, parsed[key]))
                for key, value in original.items()
            )
        if isinstance(original, list):
            return (
                isinstance(parsed, list)
                and len(original) == len(parsed)
                and all(retained(a, b) for a, b in zip(original, parsed, strict=True))
            )
        return original == parsed

    if not retained(schema, restored):
        raise ReplayUnsupported(
            "tool_schema_unavailable",
            "Inspect would discard unsupported recorded schema fields; replay cannot alter the tool definition.",
        )
    return info


def extract_recorded_tool_catalog(events, records, source_index):
    by_id = {r["id"]: r["raw"] for r in records if isinstance(r.get("raw"), dict)}
    future = {}
    for e in events:
        rid = e.get("metadata", {}).get("sourceRecordId")
        raw = by_id.get(rid, {})
        if e["index"] > source_index and raw.get("event") == "model":
            future.setdefault(rid, raw)
    if not future:
        raise ReplayUnsupported(
            "tool_schema_unavailable", "No future recorded model tool definitions are available."
        )
    baseline, definitions, source_ids = None, [], []
    for rid, raw in future.items():
        tools = raw.get("tools")
        if not isinstance(tools, list) or not tools:
            code = "dynamic_tool_catalog_unsupported" if baseline else "tool_schema_unavailable"
            raise ReplayUnsupported(
                code, "Explicit tool definitions are missing or change in the future run."
            )
        values, current = [], []
        for tool in tools:
            if (
                not isinstance(tool, dict)
                or not isinstance(tool.get("parameters"), dict)
                or tool.get("parameters", {}).get("type") != "object"
                or not tool.get("name")
            ):
                raise ReplayUnsupported(
                    "tool_schema_unavailable", "A recorded tool lacks an explicit parameter schema."
                )
            try:
                recorded_tool_info(tool["name"], tool.get("description"), tool["parameters"])
            except ValueError as exc:
                raise ReplayUnsupported(
                    "tool_schema_unavailable",
                    "Recorded tool schema is not supported by this Inspect version.",
                ) from exc
            if tool.get("options"):
                raise ReplayUnsupported(
                    "tool_schema_unavailable",
                    "Provider-specific tool execution options are not supported for recorded replay.",
                )
            values.append({k: tool.get(k) for k in ("name", "description", "parameters")})
            current.append(
                RecordedToolDefinition(
                    name=tool["name"],
                    description=tool.get("description"),
                    parameters_schema=tool["parameters"],
                    source_record_id=rid,
                )
            )
        if len({t.name for t in current}) != len(current):
            raise ReplayUnsupported(
                "tool_schema_unavailable", "Duplicate tool definitions are ambiguous."
            )
        digest = canonical_hash(sorted(values, key=lambda t: t["name"]))
        if baseline is not None and baseline != digest:
            raise ReplayUnsupported(
                "dynamic_tool_catalog_unsupported",
                "Tool availability or schemas change during the relevant future run.",
            )
        baseline, definitions = digest, definitions or current
        source_ids.append(rid)
    return RecordedToolCatalog(
        tools=definitions, canonical_hash=baseline, source_record_ids=source_ids
    )


def tool_result_message(call_id, name, result, error):
    # Text and explicit text blocks are faithfully representable. Never stringify tensors,
    # binary data, arbitrary objects or multimodal payloads to make replay continue.
    if result is None and error is not None:
        result = ""  # An error with no successful content stays an error, never success text.
    if not isinstance(result, str) and not (
        isinstance(result, list)
        and all(
            isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
            for b in result
        )
    ):
        raise ReplayUnsupported(
            "unsupported_tool_result", "Only recorded text tool results are supported."
        )
    if error is not None and not isinstance(error, dict):
        raise ReplayUnsupported(
            "unsupported_tool_result",
            "The recorded tool error lacks a faithful structured representation.",
        )
    value = {"role": "tool", "tool_call_id": call_id, "function": name, "content": result}
    if error is not None:
        value["error"] = error
    try:
        ChatMessageTool.model_validate(value)
    except ValueError as exc:
        raise ReplayUnsupported(
            "unsupported_tool_result", "Inspect cannot represent this tool result/error faithfully."
        ) from exc
    return copy.deepcopy(value)
