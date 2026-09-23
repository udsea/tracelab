from difflib import SequenceMatcher

from tracelab.storage.queries import trajectory_filter


def signature(event):
    return (
        event["type"],
        event.get("role"),
        (event.get("tool") or {}).get("name"),
        event.get("content") or "",
    )


def compare_events(left: list[dict], right: list[dict], intervention_index=None):
    a, b = [signature(e) for e in left], [signature(e) for e in right]
    prefix = 0
    while prefix < min(len(a), len(b)) and a[prefix] == b[prefix]:
        prefix += 1
    # Exact matches anchor the cheap alignment; content similarity only pairs nearby same-kind events.
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    rows = []
    divergence = None
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        for k in range(max(i2 - i1, j2 - j1)):
            left_event = left[i1 + k] if i1 + k < i2 else None
            right_event = right[j1 + k] if j1 + k < j2 else None
            changed = tag != "equal"
            similarity = None
            if (
                left_event
                and right_event
                and signature(left_event)[:3] == signature(right_event)[:3]
            ):
                similarity = round(
                    SequenceMatcher(
                        None,
                        (left_event.get("content") or "")[:2000],
                        (right_event.get("content") or "")[:2000],
                    ).ratio(),
                    3,
                )
            is_intervention = bool(
                right_event and right_event.get("metadata", {}).get("intervened")
            ) or bool(
                left_event
                and intervention_index is not None
                and left_event["index"] <= intervention_index
                and changed
            )
            if changed and not is_intervention and divergence is None:
                divergence = {
                    "left": left_event["index"] if left_event else None,
                    "right": right_event["index"] if right_event else None,
                }

            def brief(e):
                if not e:
                    return None
                return {
                    "id": e["id"],
                    "index": e["index"],
                    "type": e["type"],
                    "role": e.get("role"),
                    "toolName": (e.get("tool") or {}).get("name"),
                    "preview": (e.get("content") or "")[:500],
                }

            rows.append(
                {
                    "left": brief(left_event),
                    "right": brief(right_event),
                    "changed": changed,
                    "intervention": is_intervention,
                    "similarity": similarity,
                }
            )
    return {
        "commonPrefix": prefix,
        "interventionIndex": intervention_index,
        "firstBehaviouralDivergence": divergence,
        "rows": rows,
        "method": "Exact event anchors and local content similarity; heuristic, not a causal estimate.",
    }


def group_comparison(db, workspace_id, groups):
    result = []
    for group in groups:
        where, args = trajectory_filter(
            workspace_id, group.get("experimentId"), group.get("filters")
        )
        counts = db.query(
            f"""SELECT count(*), count(*) FILTER (WHERE data->>'status'='success'),
            count(*) FILTER (WHERE data->>'status'='error'), avg(TRY_CAST(data->>'totalTokens' AS DOUBLE)),
            count(*) FILTER (WHERE data->>'status' IN ('success','failure')) FROM trajectories WHERE {where}""",
            args,
        )[0]
        classifier = []
        # Aggregate within trajectory first so long trajectories do not dominate the group mean.
        for row in db.query(
            f"""SELECT classifier_id, avg(mean_score), avg(CASE WHEN mean_score > .8 THEN 1.0 ELSE 0.0 END), count(*)
            FROM (SELECT classifier_id, trajectory_id, avg(TRY_CAST(data->'output'->>'score' AS DOUBLE)) mean_score
                  FROM current_classifier_results WHERE trajectory_id IN (SELECT id FROM trajectories WHERE {where})
                  AND (data->'output'->>'score') IS NOT NULL GROUP BY classifier_id, trajectory_id)
            GROUP BY classifier_id""",
            args,
        ):
            classifier.append(
                {"classifierId": row[0], "meanScore": row[1], "aboveThreshold": row[2], "n": row[3]}
            )
        result.append(
            {
                "group": group,
                "trajectories": counts[0],
                "success": counts[1],
                "errors": counts[2],
                "meanTokens": counts[3],
                "scoredOutcomes": counts[4],
                "successRate": counts[1] / counts[4] if counts[4] else None,
                "classifiers": classifier,
            }
        )
    return result


def group_members(db, workspace_id, group, metric, offset=0):
    where, args = trajectory_filter(workspace_id, group.get("experimentId"), group.get("filters"))
    extra = {
        "success": "data->>'status'='success'",
        "errors": "data->>'status'='error'",
        "meanTokens": "TRY_CAST(data->>'totalTokens' AS DOUBLE) IS NOT NULL",
        "scoredOutcomes": "data->>'status' IN ('success','failure')",
        "successRate": "data->>'status' IN ('success','failure')",
        "trajectories": "TRUE",
    }.get(metric)
    if extra is None:
        extra = "id IN (SELECT trajectory_id FROM current_classifier_results WHERE classifier_id = ? AND (data->'output'->>'score') IS NOT NULL)"
        args.append(metric)
    where += " AND (" + extra + ")"
    return {
        "items": db.list("trajectories", where, args, 50, max(0, int(offset))),
        "total": db.query(f"SELECT count(*) FROM trajectories WHERE {where}", args)[0][0],
    }
