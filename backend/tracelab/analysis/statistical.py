"""Rolling distribution shifts (total variation), entropy and robust spike scores."""

import math
from collections import Counter
from statistics import median

from tracelab.analysis.rules import signature


def features(events, semantic, selected):
    counts = Counter()
    for e, s in zip(events, semantic, strict=True):
        if "event" in selected:
            counts[
                "event:" + ("opaque_reasoning" if s.presentation_class == "opaque" else e["type"])
            ] += 1
        if "tool" in selected:
            counts["tool:" + ((e.get("tool") or {}).get("name") or "none")] += 1
        if "agent" in selected:
            counts["agent:" + (s.agent_id or "unknown")] += 1
        if "error" in selected:
            counts["error:" + str(bool(s.error) or s.tool_success is False)] += 1
    return {k: v / max(1, len(events)) for k, v in counts.items()}


def statistical_matches(events, semantic, config):
    window = max(3, min(500, int(config.get("window", 30))))
    stride = max(1, int(config.get("stride", max(1, window // 3))))
    selected = config.get("features", ["event", "tool", "agent", "error"])
    threshold = {"low": 0.5, "medium": 0.3, "high": 0.15}.get(
        config.get("sensitivity", "medium"), 0.3
    )
    operators = config.get(
        "operators",
        [
            "change_point",
            "repetition",
            "error_loop",
            "tool_entropy",
            "action_novelty",
            "latency_spike",
            "token_spike",
        ],
    )
    last_peak = -window
    for i in range(window, len(events) - window + 1, stride):
        before = features(events[i - window : i], semantic[i - window : i], selected)
        after = features(events[i : i + window], semantic[i : i + window], selected)
        changed = sorted(
            ((k, after.get(k, 0) - before.get(k, 0)) for k in before.keys() | after.keys()),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        score = sum(abs(v) for _, v in changed) / (2 * max(1, len(selected)))
        if "change_point" in operators and score >= threshold and i - last_peak >= window:
            last_peak = i
            yield {
                "start": events[i]["index"],
                "end": events[i]["index"],
                "score": score,
                "label": "behavioral_change_point",
                "evidence": [e["id"] for e in events[i - window : i + window]],
                "details": {
                    "before": before,
                    "after": after,
                    "largestChangedFeatures": changed[:8],
                    "algorithm": "mean total variation across categorical feature families",
                    "window": window,
                },
            }
    seen = set()
    novelty = {}
    for event in events:
        if event["type"] == "tool_call":
            key = signature(event)
            novelty[event["id"]] = key not in seen
            seen.add(key)
    durations = [s.duration_ms for s in semantic if s.duration_ms is not None]
    tokens = [
        sum(v for v in usage.values() if isinstance(v, (int, float)))
        if any(isinstance(v, (int, float)) for v in usage.values())
        else None
        for usage in ((e.get("tokenUsage") or {}) for e in events)
    ]
    for i in range(0, len(events), stride):
        block, sem = events[i : i + window], semantic[i : i + window]
        if not block:
            continue
        calls = [signature(e) for e in block if e["type"] == "tool_call"]
        freq = Counter(calls)
        tool_counts = Counter(name for name, _ in calls)
        entropy = (
            -sum((n / len(calls)) * math.log2(n / len(calls)) for n in tool_counts.values())
            if calls
            else None
        )
        candidates = {
            "repetition": (max(freq.values()) / len(calls) if len(calls) >= 3 else None),
            "error_loop": sum(bool(s.error) or s.tool_success is False for s in sem) / len(sem),
            "tool_entropy": entropy,
            "action_novelty": sum(novelty.get(e["id"], False) for e in block) / len(calls)
            if calls
            else None,
        }
        for label, score in candidates.items():
            if label in operators and score is not None:
                yield {
                    "start": block[0]["index"],
                    "end": block[-1]["index"],
                    "score": score,
                    "label": label,
                    "evidence": [e["id"] for e in block],
                    "details": {
                        "window": window,
                        "toolCounts": dict(tool_counts),
                        "unit": "bits" if label == "tool_entropy" else "fraction",
                    },
                }
    for label, population, values in (
        ("latency_spike", durations, [s.duration_ms for s in semantic]),
        ("token_spike", [v for v in tokens if v is not None], tokens),
    ):
        if label not in operators or len(population) < 5:
            continue
        center = median(population)
        mad = median(abs(x - center) for x in population)
        for e, value in zip(events, values, strict=True):
            if value is not None and value > center + max(3 * 1.4826 * mad, center * 2, 1):
                yield {
                    "start": e["index"],
                    "end": e["index"],
                    "score": (value - center) / max(1.4826 * mad, 1),
                    "label": label,
                    "evidence": [e["id"]],
                    "details": {
                        "value": value,
                        "median": center,
                        "mad": mad,
                        "algorithm": "median absolute deviation",
                        "unit": "robust deviations",
                    },
                }
