"""Post-execution analysis is a separate job; analysis failure never changes fork outcome."""

import asyncio

from tracelab.analysis.contrastive import compare, completed_rules
from tracelab.analysis.detectors import RuleDetector, StatisticalDetector
from tracelab.analysis.projection import signals
from tracelab.models.domain import Job


async def analyze_branches(service, fork, job):
    definitions = completed_rules(service.db, fork.source_trajectory_id)
    for signal in signals(service.db, fork.source_trajectory_id):
        definition = signal.get("provenance", {}).get("definition")
        if definition and signal["sourceType"] in ("rule", "statistical"):
            definitions[definition["id"]] = definition

    for tid in fork.child_trajectory_ids:
        for definition in definitions.values():
            detector = RuleDetector if definition["detectorType"] == "rule" else StatisticalDetector
            found = await detector(service).run([tid], definition)
            for item in found:
                item.provenance["jobId"] = job.id
                item.provenance["branchAnalysis"] = True
            service.db.put_many("analysis_signals", found)
            job.metadata.setdefault("completedDetectors", []).append(
                {"trajectoryId": tid, "definition": definition}
            )
            service.jobs.save(job)
        result = await compare(service, fork.source_trajectory_id, tid)
        service.db.put(
            "branch_comparisons",
            {
                "id": f"{fork.id}:{tid}",
                "trajectoryId": tid,
                "forkId": fork.id,
                "comparison": result,
            },
        )
        job.completed += 1
        service.jobs.save(job)


def schedule_branch_analysis(service, fork):
    definitions = completed_rules(service.db, fork.source_trajectory_id)

    return service.jobs.start(
        Job(
            kind="analysis",
            name="Observed branch comparison",
            total=len(fork.child_trajectory_ids),
            metadata={
                "forkId": fork.id,
                "trajectoryIds": fork.child_trajectory_ids,
                "definitions": list(definitions),
                "llmPolicy": "Existing results compared; LLM detectors are never silently rerun",
            },
        ),
        lambda job: analyze_branches(service, fork, job),
    )


def schedule_experiment_analysis(service, fork_experiment):
    from tracelab.models.domain import Fork

    if service.jobs.closing:
        raise ValueError("Backend is closing; completed execution artifacts remain available")
    fork_ids = list(fork_experiment.fork_ids)
    previous_id = fork_experiment.metadata.get("analysisJobId")

    async def run(job):
        # If a resumed experiment finishes before its preceding analysis, join that
        # cheap job first and consult persisted comparisons to avoid duplicate work.
        previous = service.jobs.tasks.get(previous_id)
        if previous and previous is not asyncio.current_task():
            await asyncio.shield(previous)
        for fid in fork_ids:
            # Fork metadata can contain the full context: load only one cell at a time.
            fork = Fork.model_validate(service.db.get("forks", fid))
            original_count = len(fork.child_trajectory_ids)
            fork.child_trajectory_ids = [
                tid
                for tid in fork.child_trajectory_ids
                if not service.db.maybe("branch_comparisons", f"{fork.id}:{tid}")
            ]
            job.completed += original_count - len(fork.child_trajectory_ids)
            service.jobs.save(job)
            await analyze_branches(service, fork, job)

    return service.jobs.start(
        Job(
            kind="analysis",
            name="Experiment branch analysis",
            total=service.db.read(
                "SELECT count(*) FROM fork_trials WHERE experiment_id=? AND trajectory_id IS NOT NULL",
                [fork_experiment.id],
            )[0][0],
            metadata={
                "forkExperimentId": fork_experiment.id,
                "llmPolicy": "Existing results compared; LLM detectors are never silently rerun",
            },
        ),
        run,
    )
