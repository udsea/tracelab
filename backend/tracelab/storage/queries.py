import json

from tracelab.storage.database import Database


def trajectory_filter(workspace_id=None, experiment_id=None, filters=None):
    clauses, args = ["TRUE"], []
    if workspace_id:
        clauses.append("experiment_id IN (SELECT id FROM experiments WHERE workspace_id = ?)")
        args.append(workspace_id)
    if experiment_id:
        clauses.append("experiment_id = ?")
        args.append(experiment_id)
    strings = {
        "sample": "sampleId",
        "condition": "condition",
        "model": "model",
        "status": "status",
        "parent": "parentTrajectoryId",
    }
    numbers = {"tokens": "totalTokens", "duration": "durationMs"}
    ops = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    for item in filters or []:
        field, op, value = item["field"], ops.get(item.get("op", "eq")), item.get("value")
        if item.get("op") == "contains" and field in strings:
            clauses.append(f"contains(lower(data->>'{strings[field]}'), lower(?))")
            args.append(str(value))
            continue
        if not op:
            raise ValueError("Unsupported filter operation")
        if field in strings:
            clauses.append(f"(data->>'{strings[field]}') {op} ?")
            args.append(str(value))
        elif field in numbers:
            clauses.append(f"TRY_CAST(data->>'{numbers[field]}' AS DOUBLE) {op} ?")
            args.append(float(value))
        elif field == "score":
            # Scorers may expose a scalar or a {value: ...} object. Name is passed as data.
            clauses.append(
                f"TRY_CAST(COALESCE(json_extract(data->'scores', ?)->>'value', json_extract_string(data->'scores', ?)) AS DOUBLE) {op} ?"
            )
            pointer = "/" + str(item.get("key", "")).replace("~", "~0").replace("/", "~1")
            args += [pointer, pointer, float(value)]
        elif field in ("classifier", "classifierLabel"):
            expression = (
                "TRY_CAST(r.data->'output'->>'score' AS DOUBLE)"
                if field == "classifier"
                else "(r.data->'output'->>'label')"
            )
            clauses.append(
                f"id IN (SELECT trajectory_id FROM current_classifier_results r WHERE classifier_id = ? AND {expression} {op} ?)"
            )
            args += [item.get("key"), float(value) if field == "classifier" else str(value)]
        elif field == "annotation":
            clauses.append(
                "id IN (SELECT trajectory_id FROM annotations WHERE (data->>'label') = ?)"
            )
            args.append(str(value))
        elif field == "error":
            clauses.append(
                "((data->>'status') = 'error' OR id IN (SELECT trajectory_id FROM events WHERE (data->>'type') = 'error' OR (data->'tool'->>'error') IS NOT NULL))"
            )
        elif field == "forkStatus":
            clauses.append(
                "(data->>'forkId') IN (SELECT id FROM forks WHERE (data->>'status') = ?)"
            )
            args.append(str(value))
        else:
            raise ValueError(f"Unsupported filter: {field}")
    return " AND ".join(f"({x})" for x in clauses), args


def list_trajectories(
    db: Database, workspace_id=None, experiment_id=None, filters=None, offset=0, limit=100
):
    where, args = trajectory_filter(workspace_id, experiment_id, filters)
    total = db.query(f"SELECT count(*) FROM trajectories WHERE {where}", args)[0][0]
    return {
        "items": db.list(
            "trajectories",
            where,
            args,
            min(int(limit), 500),
            int(offset),
            order="data->>'sampleId', id",
        ),
        "total": total,
    }


def event_page(db, trajectory_id, offset=0, limit=100, mode="all", query="", start=None, end=None):
    where, args = ["trajectory_id = ?"], [trajectory_id]
    modes = {"tools": ["tool_call", "tool_result"], "reasoning": ["reasoning"], "errors": ["error"]}
    if mode in modes:
        kinds = modes[mode]
        where.append(
            "((data->>'type') IN ("
            + ",".join("?" for _ in kinds)
            + ")"
            + (" OR (data->'tool'->>'error') IS NOT NULL" if mode == "errors" else "")
            + ")"
        )
        args += kinds
    if query:
        where.append("contains(lower(search_text), lower(?))")
        args.append(query)
    if start is not None:
        where.append("event_index >= ?")
        args.append(int(start))
    if end is not None:
        where.append("event_index <= ?")
        args.append(int(end))
    clause = " AND ".join(where)
    total = db.query(f"SELECT count(*) FROM events WHERE {clause}", args)[0][0]
    rows = db.query(
        f"""SELECT id, event_index, data->>'type', data->>'role',
        substring(COALESCE(NULLIF(data->>'content', ''), data->'tool'->>'error', data->'tool'->>'arguments'), 1, 280), data->>'timestamp', data->'tool'->>'name',
        data->'tool'->>'error', data->>'tokenUsage', data->'metadata'->>'intervened'
        FROM events WHERE {clause} ORDER BY event_index LIMIT ? OFFSET ?""",
        args + [min(int(limit), 500), max(0, int(offset))],
    )
    return {
        "total": total,
        "offset": offset,
        "items": [
            {
                "id": r[0],
                "trajectoryId": trajectory_id,
                "index": r[1],
                "type": r[2],
                "role": r[3],
                "preview": r[4] or "",
                "timestamp": r[5],
                "toolName": r[6],
                "hasError": bool(r[7]) or r[2] == "error",
                "tokenUsage": json.loads(r[8]) if r[8] else None,
                "intervened": r[9] == "true",
            }
            for r in rows
        ],
    }


def search(db, workspace_id, query, limit=100):
    if not query.strip():
        return {"items": [], "total": 0}
    clause = """contains(lower(search_text), lower(?)) AND trajectory_id IN
        (SELECT id FROM trajectories WHERE experiment_id IN
            (SELECT id FROM experiments WHERE workspace_id = ?))"""
    rows = db.query(
        f"""SELECT id, trajectory_id, event_index, data->>'type', search_text
        FROM events WHERE {clause} ORDER BY trajectory_id, event_index LIMIT ?""",
        [query, workspace_id, limit],
    )
    items = [
        {
            "id": r[0],
            "trajectoryId": r[1],
            "index": r[2],
            "type": r[3],
            "preview": excerpt(r[4], query),
        }
        for r in rows
    ]
    annotations = db.query(
        f"SELECT data FROM annotations WHERE {clause} LIMIT ?", [query, workspace_id, limit]
    )
    for (raw,) in annotations:
        ann = json.loads(raw)
        items.append(
            {
                "id": ann["id"],
                "trajectoryId": ann["trajectoryId"],
                "index": ann["startEventIndex"],
                "type": "annotation",
                "preview": ann["label"] + ": " + (ann.get("note") or ""),
            }
        )
    total = db.query(f"SELECT count(*) FROM events WHERE {clause}", [query, workspace_id])[0][
        0
    ] + len(annotations)
    unindexed = db.query(
        """SELECT count(*) FROM trajectories WHERE (data->>'loaded') != 'true' AND
        experiment_id IN (SELECT id FROM experiments WHERE workspace_id = ?)""",
        [workspace_id],
    )[0][0]
    return {"items": items[:limit], "total": total, "unindexedTrajectories": unindexed}


def excerpt(text, needle):
    pos = text.lower().find(needle.lower())
    start = max(0, pos - 60)
    return ("…" if start else "") + text[start : start + 240]


def result_summaries(db, trajectory_id, event_index=None):
    where, args = "trajectory_id = ?", [trajectory_id]
    if event_index is not None:
        where += " AND event_index <= ? AND TRY_CAST(data->>'endEventIndex' AS INTEGER) >= ?"
        args += [event_index, event_index]
    # Never ship the exact prompt, input payload, or provider response until explicitly opened.
    rows = db.query(
        f"""SELECT json_object(
        'id', id, 'classifierId', classifier_id, 'trajectoryId', trajectory_id,
        'runId', data->>'runId', 'startEventIndex', event_index,
        'endEventIndex', TRY_CAST(data->>'endEventIndex' AS INTEGER),
        'output', data->'output', 'error', data->>'error',
        'cached', TRY_CAST(data->>'cached' AS BOOLEAN), 'createdAt', data->>'createdAt',
        'cacheKey', data->>'cacheKey') FROM current_classifier_results WHERE {where}
        ORDER BY event_index, classifier_id""",
        args,
    )
    return [json.loads(row[0]) for row in rows]
