"""ATIF v1.x: one-pass streaming of steps and embedded agents, preserving their graph."""

import ijson
from ijson.common import ObjectBuilder

from tracelab.importers.base import DetectionResult
from tracelab.importers.common import EventBuilder, StreamImporter, first_record


class ATIFImporter(StreamImporter):
    name = "atif"

    def detect(self, source, ref):
        row = first_record(source, ref)
        matched = str(row.get("schema_version", "")).startswith("ATIF-")
        return DetectionResult(
            confidence=0.99 if matched else 0,
            format=self.name,
            reason="ATIF schema_version" if matched else "No ATIF version marker",
        )

    def iter_events(self, source, run, trajectory_id):
        builder = EventBuilder(trajectory_id)
        frames, seen, delegated = [], set(), {}
        capture = None

        def scope(frame):
            if frame.get("scope"):
                return []
            raw = frame["metadata"]
            identity = str(raw.get("trajectory_id") or raw.get("session_id") or frame["path"])
            if identity in seen:
                raise ValueError("ATIF embedded trajectory IDs must be unique")
            seen.add(identity)
            frame["identity"] = identity
            parent = frame.get("parent")
            parents = [parent["scope"]] if parent else []
            if identity in delegated:
                parents.append(delegated[identity])
            event = builder.emit(
                "environment",
                (raw.get("agent") or {}).get("name") or identity,
                external=f"atif-agent:{identity}",
                parents=parents,
                raw=dict(raw),
                agent=identity,
                structuralKind="agent",
                agentIdentity=raw.get("agent"),
                trajectoryIdentity=identity,
                sessionId=raw.get("session_id"),
                sourcePointer=frame["path"],
                scopePhase="start",
            )
            frame["scope"] = event.id
            return [event]

        def step(frame, raw):
            identity = frame["identity"]
            step_id = raw.get("step_id", builder.index)
            anchor = builder.emit(
                "environment",
                f"Step {step_id}",
                external=f"atif-step:{identity}:{step_id}",
                parents=[frame["scope"]],
                raw=raw,
                agent=identity,
                structuralKind="step",
                metrics=raw.get("metrics"),
                model=raw.get("model_name"),
                stamp=raw.get("timestamp"),
            )
            yield anchor
            parent = [anchor.id]
            role = {"agent": "assistant", "user": "user", "system": "system"}.get(
                raw.get("source"), "assistant"
            )
            if raw.get("reasoning_content"):
                yield builder.emit(
                    "reasoning",
                    raw["reasoning_content"],
                    role="assistant",
                    parents=parent,
                    agent=identity,
                    raw=raw,
                    stamp=raw.get("timestamp"),
                )
            if raw.get("message"):
                yield builder.emit(
                    role,
                    raw["message"],
                    role=role,
                    parents=parent,
                    agent=identity,
                    raw=raw,
                    stamp=raw.get("timestamp"),
                )
            for call in raw.get("tool_calls") or []:
                cid = call["tool_call_id"]
                event = builder.emit(
                    "tool_call",
                    call.get("arguments"),
                    parents=parent,
                    role="assistant",
                    agent=identity,
                    raw=call,
                    tool={
                        "name": call["function_name"],
                        "callId": cid,
                        "arguments": call.get("arguments"),
                    },
                    stamp=raw.get("timestamp"),
                )
                builder.calls[(identity, cid)] = (event.id, call["function_name"])
                yield event
            for result in (raw.get("observation") or {}).get("results", []):
                cid = result.get("source_call_id")
                call = builder.calls.get((identity, cid))
                parents = [call[0]] if call else parent.copy()
                refs = result.get("subagent_trajectory_ref") or []
                refs = [refs] if isinstance(refs, dict) else refs
                for ref in refs:
                    child = ref.get("trajectory_id")
                    if child and not ref.get("trajectory_path"):
                        delegated[child] = call[0] if call else anchor.id
                        parents.append(builder.event_id(f"atif-agent:{child}"))
                yield builder.emit(
                    "tool_result" if cid else "environment",
                    result.get("content"),
                    parents=parents,
                    agent=identity,
                    raw=result,
                    tool={
                        "name": call[1] if call else "tool",
                        "callId": cid,
                        "result": result.get("content"),
                    }
                    if cid
                    else None,
                    subagentReferences=refs,
                    stamp=raw.get("timestamp"),
                )

        with source.open(run.source) as stream:
            for prefix, event, value in ijson.parse(stream, use_float=True):
                if capture:
                    capture["builder"].event(event, value)
                    if prefix == capture["prefix"] and event in ("end_map", "end_array"):
                        raw = capture["builder"].value
                        if capture["kind"] == "step":
                            yield from step(frames[-1], raw)
                        else:
                            frames[-1]["metadata"][capture["key"]] = raw
                        capture = None
                    continue
                if event == "start_map" and (
                    not frames
                    and prefix == ""
                    or frames
                    and prefix
                    == frames[-1]["prefix"]
                    + ("." if frames[-1]["prefix"] else "")
                    + "subagent_trajectories.item"
                ):
                    parent = frames[-1] if frames else None
                    if parent:
                        yield from scope(parent)
                        parent["children"] += 1
                    frames.append(
                        {
                            "prefix": prefix,
                            "path": f"{parent['path']}/subagent_trajectories/{parent['children'] - 1}"
                            if parent
                            else "$",
                            "metadata": {},
                            "children": 0,
                            "parent": parent,
                        }
                    )
                    continue
                if not frames:
                    continue
                frame = frames[-1]
                relative = prefix[len(frame["prefix"]) :].lstrip(".")
                if relative == "steps.item" and event == "start_map":
                    yield from scope(frame)
                    capture = {"prefix": prefix, "kind": "step", "builder": ObjectBuilder()}
                    capture["builder"].event(event, value)
                elif (
                    relative
                    and "." not in relative
                    and relative not in ("steps", "subagent_trajectories")
                ):
                    if event in ("start_map", "start_array"):
                        capture = {
                            "prefix": prefix,
                            "kind": "metadata",
                            "key": relative,
                            "builder": ObjectBuilder(),
                        }
                        capture["builder"].event(event, value)
                    elif event in ("string", "number", "boolean", "null"):
                        frame["metadata"][relative] = value
                elif prefix == frame["prefix"] and event == "end_map":
                    yield from scope(frame)
                    yield builder.emit(
                        "environment",
                        "Trajectory metadata",
                        parents=[frame["scope"]],
                        agent=frame["identity"],
                        raw=frame["metadata"],
                        structuralKind="agent",
                        scopePhase="end",
                        sourcePointer=frame["path"],
                        continuation=frame["metadata"].get("continued_trajectory_ref"),
                        metrics=frame["metadata"].get("final_metrics"),
                    )
                    frames.pop()
