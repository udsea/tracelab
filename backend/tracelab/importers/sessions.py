from tracelab.importers.base import DetectionResult
from tracelab.importers.common import EventBuilder, StreamImporter, first_record, json_lines, text


class HFSessionTraceImporter(StreamImporter):
    name = "sts"

    def detect(self, source, ref):
        row = first_record(source, ref)
        sts = (
            row.get("type") == "session" and ("harness" in row or "version" in row) and "id" in row
        )
        codex = row.get("type") == "session_meta" and isinstance(row.get("payload"), dict)
        claude = (
            row.get("type") in ("user", "assistant") and "sessionId" in row and "message" in row
        )
        return DetectionResult(
            format=self.name,
            confidence=0.98 if sts else 0.94 if codex or claude else 0,
            reason="Session header / supported raw session envelope"
            if sts or codex or claude
            else "No session signature",
        )

    def iter_events(self, source, run, trajectory_id):
        b = EventBuilder(trajectory_id)
        for line, row in json_lines(source, run.source):
            kind = row.get("type")
            external = row.get("uuid") or row.get("id") or f"line:{line}"
            parent = row.get("parentUuid") or row.get("parentId")
            parents = [b.event_id(parent)] if parent else []
            if kind in ("session", "session_meta"):
                yield b.emit(
                    "environment",
                    "Session metadata",
                    external=external,
                    raw=row,
                    harness=row.get("harness") or (row.get("payload") or {}).get("originator"),
                    stamp=row.get("timestamp"),
                )
                continue
            msg = row.get("message")
            if kind == "response_item":
                payload = row.get("payload") or {}
                if payload.get("type") == "message":
                    msg = {
                        "role": payload.get("role"),
                        "content": payload.get("content"),
                        "timestamp": row.get("timestamp"),
                    }
                elif payload.get("type") in ("function_call", "custom_tool_call"):
                    msg = {
                        "role": "assistant",
                        "toolCalls": [
                            {
                                "id": payload.get("call_id"),
                                "function": {
                                    "name": payload.get("name"),
                                    "arguments": payload.get("arguments", payload.get("input")),
                                },
                            }
                        ],
                    }
                elif payload.get("type") in ("function_call_output", "custom_tool_call_output"):
                    msg = {
                        "role": "tool",
                        "toolCallId": payload.get("call_id"),
                        "content": payload.get("output"),
                    }
                elif payload.get("type") == "reasoning":
                    yield b.emit(
                        "reasoning",
                        payload.get("summary") or payload.get("content"),
                        raw=row,
                        external=external,
                        stamp=row.get("timestamp"),
                    )
                    continue
            if isinstance(msg, dict):
                msg = {**msg, "timestamp": msg.get("timestamp", row.get("timestamp"))}
                content = msg.get("content")
                if isinstance(content, list):
                    # Claude and Pi content blocks have the same documented text/tool shape.
                    blocks = content
                    msg["content"] = "\n".join(
                        text(x.get("text"))
                        for x in blocks
                        if isinstance(x, dict)
                        and x.get("type") in ("text", "input_text", "output_text")
                    )
                    block_reasoning = "\n".join(
                        text(x.get("thinking", x.get("text")))
                        for x in blocks
                        if isinstance(x, dict) and x.get("type") in ("thinking", "reasoning")
                    )
                    msg["reasoningContent"] = "\n".join(
                        filter(None, [msg.get("reasoningContent"), block_reasoning])
                    )
                    msg["toolCalls"] = (msg.get("toolCalls") or msg.get("tool_calls") or []) + [
                        {
                            "id": x.get("id"),
                            "function": {
                                "name": x.get("name"),
                                "arguments": x.get("input", x.get("arguments")),
                            },
                        }
                        for x in blocks
                        if isinstance(x, dict) and x.get("type") in ("tool_use", "toolCall")
                    ]
                    for block in blocks:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            yield from b.message(
                                {
                                    "role": "tool",
                                    "toolCallId": block.get("tool_use_id"),
                                    "content": block.get("content"),
                                },
                                raw=row,
                                parents=parents,
                            )
                if msg.get("role") == "toolResult":
                    msg["role"] = "tool"
                yield from b.message(
                    msg, raw=row, external=external, parents=parents, agent=row.get("agentId")
                )
            else:
                yield b.emit(
                    "other",
                    kind,
                    external=external,
                    parents=parents,
                    raw=row,
                    stamp=row.get("timestamp"),
                )
