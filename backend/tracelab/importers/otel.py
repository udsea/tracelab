"""OTLP JSON spans stay spans; GenAI messages are children of their owning span."""

import json

import ijson
from ijson.common import ObjectBuilder

from tracelab.importers.base import DetectionResult
from tracelab.importers.common import EventBuilder, StreamImporter, first_record, text


def any_value(value):
    if not isinstance(value, dict):
        return value
    for kind in ("stringValue", "boolValue", "intValue", "doubleValue", "bytesValue"):
        if kind in value:
            return int(value[kind]) if kind == "intValue" else value[kind]
    if "arrayValue" in value:
        return [any_value(v) for v in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return attributes(value["kvlistValue"].get("values", []))
    return value


def attributes(items):
    return {item["key"]: any_value(item.get("value")) for item in items if "key" in item}


def parse_messages(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


class OpenTelemetryImporter(StreamImporter):
    name = "otel"

    def detect(self, source, ref):
        row = first_record(source, ref)
        match = "resourceSpans" in row or "resource_spans" in row
        return DetectionResult(
            format=self.name,
            confidence=0.98 if match else 0,
            reason="OTLP JSON resource spans" if match else "No OTLP export structure",
        )

    def iter_events(self, source, run, trajectory_id):
        b = EventBuilder(trajectory_id)
        resource, scope = {}, {}
        capture = None
        with source.open(run.source) as stream:
            for prefix, event, value in ijson.parse(stream, use_float=True):
                if capture:
                    capture["builder"].event(event, value)
                    if prefix == capture["prefix"] and event == "end_map":
                        raw = capture["builder"].value
                        if capture["kind"] == "resource":
                            resource = raw
                        elif capture["kind"] == "scope":
                            scope = raw
                        else:
                            yield from self.span(b, raw, resource, scope)
                        capture = None
                    continue
                if event == "start_map" and prefix in ("resourceSpans.item", "resource_spans.item"):
                    resource, scope = {}, {}
                if event == "start_map" and (
                    prefix.endswith(".resource")
                    or prefix.endswith(".scope")
                    or prefix.endswith(".spans.item")
                ):
                    capture = {
                        "prefix": prefix,
                        "kind": "span"
                        if prefix.endswith(".spans.item")
                        else prefix.rsplit(".", 1)[-1],
                        "builder": ObjectBuilder(),
                    }
                    capture["builder"].event(event, value)

    def span(self, b, raw, resource, scope):
        attrs = attributes(raw.get("attributes", []))
        trace = raw.get("traceId", raw.get("trace_id", ""))
        span = raw.get("spanId", raw.get("span_id"))
        if not span:
            raise ValueError("OTLP span requires spanId")
        parent = raw.get("parentSpanId", raw.get("parent_span_id"))
        parents = [b.event_id(f"otel:{trace}:{parent}")] if parent else []
        operation = attrs.get("gen_ai.operation.name", "")
        kind = (
            "tool"
            if operation == "execute_tool" or "gen_ai.tool.name" in attrs
            else "agent"
            if operation == "invoke_agent"
            else "llm"
            if operation in ("chat", "generate_content", "text_completion")
            else "retrieval"
            if "retriev" in operation
            else "workflow"
        )
        status = raw.get("status") or {}
        error = status.get("code") in (2, "STATUS_CODE_ERROR", "ERROR")
        start = raw.get("startTimeUnixNano", raw.get("start_time_unix_nano"))
        end = raw.get("endTimeUnixNano", raw.get("end_time_unix_nano"))
        agent = (
            attrs.get("gen_ai.agent.id")
            or attrs.get("gen_ai.agent.name")
            or (span if kind == "agent" else parent)
        )
        tool = (
            {
                "name": attrs.get("gen_ai.tool.name", raw.get("name", "tool")),
                "callId": attrs.get("gen_ai.tool.call.id", span),
                "arguments": attrs.get("gen_ai.tool.call.arguments"),
                "result": attrs.get("gen_ai.tool.call.result"),
                "error": status.get("message") if error else None,
            }
            if kind == "tool"
            else None
        )
        anchor = b.emit(
            "error" if error else "tool_call" if kind == "tool" else "environment",
            raw.get("name"),
            external=f"otel:{trace}:{span}",
            parents=parents,
            stamp=int(start) if start else None,
            raw=raw,
            agent=agent,
            tool=tool,
            structuralKind="span",
            spanKind=kind,
            traceId=trace,
            spanId=span,
            parentSpanId=parent,
            attributes=attrs,
            resource=resource,
            scope=scope,
            durationMs=(int(end) - int(start)) / 1e6 if end and start else None,
            model=attrs.get("gen_ai.response.model", attrs.get("gen_ai.request.model")),
        )
        anchor.token_usage = {
            "input": attrs.get("gen_ai.usage.input_tokens"),
            "output": attrs.get("gen_ai.usage.output_tokens"),
        }
        yield anchor
        for field in ("gen_ai.input.messages", "gen_ai.output.messages"):
            for msg in parse_messages(attrs.get(field)):
                if isinstance(msg, dict):
                    message = {
                        **msg,
                        "content": msg.get(
                            "content",
                            "\n".join(
                                text(p.get("content", p.get("text")))
                                for p in msg.get("parts", [])
                                if isinstance(p, dict)
                            ),
                        ),
                    }
                    yield from b.message(message, raw=msg, parents=[anchor.id], agent=agent)
        if kind == "tool" and tool["result"] is not None:
            yield b.emit(
                "tool_result",
                tool["result"],
                parents=[anchor.id],
                agent=agent,
                tool=tool,
                raw=raw,
                stamp=int(end) if end else None,
            )
        for event in raw.get("events", []):
            values = attributes(event.get("attributes", []))
            yield b.emit(
                "error" if event.get("name") == "exception" else "other",
                event.get("name"),
                parents=[anchor.id],
                agent=agent,
                raw=event,
                attributes=values,
                stamp=int(event["timeUnixNano"]) if event.get("timeUnixNano") else None,
            )
