"""Post-execution analysis is a separate job; analysis failure never changes fork outcome."""

from tracelab.analysis.contrastive import compare, completed_rules
from tracelab.analysis.detectors import RuleDetector, StatisticalDetector
from tracelab.analysis.projection import signals
from tracelab.models.domain import Job


def schedule_branch_analysis(service, fork):
    definitions = completed_rules(service.db, fork.source_trajectory_id)
    for signal in signals(service.db, fork.source_trajectory_id):
        definition = signal.get("provenance", {}).get("definition")
        if definition and signal["sourceType"] in ("rule", "statistical"):
            definitions[definition["id"]] = definition

    async def run(job):
        for tid in fork.child_trajectory_ids:
            for definition in definitions.values():
                detector = (
                    RuleDetector if definition["detectorType"] == "rule" else StatisticalDetector
                )
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
        run,
    )
