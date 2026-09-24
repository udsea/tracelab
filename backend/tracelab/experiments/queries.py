"""Compact execution summaries; deliberately no outcome/effect statistics."""

from collections import Counter


def counts(trials):
    states = Counter(t["status"] for t in trials)
    return dict(
        total=len(trials),
        finalized=sum(states[k] for k in ("complete", "error", "cancelled", "interrupted")),
        **{
            k: states[k]
            for k in ("pending", "running", "complete", "error", "cancelled", "interrupted")
        },
    )


def detail(service, id, offset=0, limit=100):
    fork_experiment = service.db.get("fork_experiments", id)
    trials = service.db.list(
        "fork_trials",
        "experiment_id=?",
        [id],
        limit=2000,
        order="CAST(data->>'scheduleOrdinal' AS INTEGER)",
    )
    cells = []
    for case in fork_experiment["cases"]:
        for arm in fork_experiment["arms"]:
            own = [t for t in trials if t["caseId"] == case["id"] and t["armId"] == arm["id"]]
            cells.append(
                dict(
                    caseId=case["id"],
                    armId=arm["id"],
                    progress=counts(own),
                    terminationCounts=dict(
                        Counter(
                            t["metadata"].get("terminationReason")
                            for t in own
                            if t["metadata"].get("terminationReason")
                        )
                    ),
                )
            )
    children = service.db.list(
        "trajectories",
        "id IN (SELECT trajectory_id FROM fork_trials WHERE experiment_id=?)",
        [id],
        limit=2000,
    )
    # PR1 single-reply records do not carry modelSteps. A completed single
    # continuation establishes one generation; failures without usage stay unknown.
    for child in children:
        if (
            child["metadata"].get("executionMode") == "single_model_continuation"
            and child["metadata"].get("executionStatus") == "complete"
        ):
            child["metadata"]["modelSteps"] = 1
    usage = {
        key: sum(c["metadata"].get(key, 0) for c in children)
        for key in ("modelSteps", "toolCalls", "replayedToolCalls", "stubbedToolCalls")
    }
    usage.update(
        modelCallReports=sum("modelSteps" in c["metadata"] for c in children),
        reportedTotalTokens=sum(c.get("totalTokens") or 0 for c in children),
        tokenReports=sum(c.get("totalTokens") is not None for c in children),
    )
    return dict(
        experiment=fork_experiment,
        armSummaries=[
            dict(armId=a["id"], progress=counts([t for t in trials if t["armId"] == a["id"]]))
            for a in fork_experiment["arms"]
        ],
        caseSummaries=[
            dict(caseId=c["id"], progress=counts([t for t in trials if t["caseId"] == c["id"]]))
            for c in fork_experiment["cases"]
        ],
        cells=cells,
        progress=counts(trials),
        executionStatusCounts=dict(
            Counter(c["metadata"].get("executionStatus", "running") for c in children)
        ),
        usage=usage,
        trials=trials[offset : offset + limit],
        offset=offset,
        limit=limit,
    )


def listing(service, workspace_id, offset=0, limit=100):
    items = service.db.list(
        "fork_experiments",
        "workspace_id=?",
        [workspace_id],
        limit=limit,
        offset=offset,
        order="data->>'createdAt' DESC",
    )
    return [
        dict(
            id=e["id"],
            name=e["name"],
            status=e["status"],
            createdAt=e["createdAt"],
            caseCount=len(e["cases"]),
            armCount=len(e["arms"]),
            replicationCount=e["replicationCount"],
            progress=counts(
                service.db.list("fork_trials", "experiment_id=?", [e["id"]], limit=2000)
            ),
        )
        for e in items
    ]
