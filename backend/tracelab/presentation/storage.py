"""Disposable, versioned local projection; never rewrites original event/source rows."""

import json

from tracelab.presentation import VERSION, prepare_event, visible_event


def prepared_events(db, trajectory_id):
    rows = db.query(
        """SELECT e.data, s.data FROM events e LEFT JOIN source_records s
        ON s.id = (e.data->'metadata'->>'sourceRecordId')
        WHERE e.trajectory_id = ? ORDER BY e.event_index""",
        [trajectory_id],
    )
    result, source_records = [], {}
    for data, source in rows:
        event = json.loads(data)
        rid = event.get("metadata", {}).get("sourceRecordId")
        if source and rid not in source_records:
            source_records[rid] = json.loads(source).get("raw") or {}
        result.append(prepare_event(event, source_records.get(rid)))
    # Old Inspect logs attach usage only to the first emitted selected-output block.
    # Siblings share both the exact source record and message identity, not mere adjacency.
    groups = {}
    for e in result:
        m = e["metadata"]
        if (
            source_records.get(m.get("sourceRecordId"), {}).get("event") == "model"
            and m.get("messageKey")
            and e.get("tokenUsage") is not None
        ):
            groups[(m["sourceRecordId"], m["messageKey"])] = (
                m.get("modelCallId") or m["sourceRecordId"] + ":output:0"
            )
    for e in result:
        m = e["metadata"]
        group = groups.get((m.get("sourceRecordId"), m.get("messageKey")))
        if group:
            m["modelCallId"] = group
    return result


def ensure_presentations(db, trajectory_id=None):
    where = "AND e.trajectory_id = ?" if trajectory_id else ""

    def missing():
        return db.query(
            f"""SELECT DISTINCT e.trajectory_id FROM events e
            LEFT JOIN event_presentations p ON e.id=p.id
            WHERE (p.id IS NULL OR (p.data->'metadata'->>'presentationVersion') IS DISTINCT FROM ?)
            {where}""",
            [VERSION] + ([trajectory_id] if trajectory_id else []),
        )

    if not missing():
        return  # Cached reads do not wait for another trajectory's first projection.
    with db.presentation_lock:
        ids = missing()
        for (tid,) in ids:
            while True:
                with db.lock:
                    revision = db.event_revisions.get(tid, 0)
                projected = [visible_event(e) for e in prepared_events(db, tid)]
                with db.lock:
                    if revision != db.event_revisions.get(tid, 0):
                        continue  # A concurrent import changed this snapshot; derive the new one.
                    db.put_many("event_presentations", projected)
                    break


def counts(db, trajectory_id):
    ensure_presentations(db, trajectory_id)
    rows = db.query(
        "SELECT data->'metadata'->>'presentationClass',count(*) FROM event_presentations WHERE trajectory_id=? GROUP BY 1",
        [trajectory_id],
    )
    values = dict(rows)
    return {
        "recorded": sum(values.values()),
        "research": values.get("semantic", 0) + values.get("opaque", 0),
        **{k: values.get(k, 0) for k in ("semantic", "runtime", "opaque")},
    }
