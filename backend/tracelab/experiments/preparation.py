"""Pure all-cell preflight, concrete binding, and deterministic scheduling."""

from tracelab.classifiers.runner import canonical_hash
from tracelab.experiments.models import ForkExperimentSpec
from tracelab.models.domain import Fork


def spec_hash(spec):
    # Design IDs define pairing; generated object IDs and runtime fields are absent.
    return canonical_hash(
        ForkExperimentSpec(
            **{name: getattr(spec, name) for name in ForkExperimentSpec.model_fields}
        ).wire()
    )


def concrete_fork(spec, case, arm_id):
    binding = next(a for a in case.arms if a.arm_id == arm_id)
    return Fork(
        source_trajectory_id=case.source_trajectory_id,
        source_event_id=case.source_event_id,
        interventions=binding.interventions,
        execution_spec=spec.execution_spec,
        model_overrides=spec.model_overrides,
        replication_count=spec.replication_count,
    )


def schedule(spec):
    for replication in range(spec.replication_count):
        for position, case in enumerate(spec.cases):
            offset = (position + replication) % len(spec.arms)
            for arm in spec.arms[offset:] + spec.arms[:offset]:
                yield case, arm, replication


async def preflight(service, spec):
    service.db.get("workspaces", spec.workspace_id)
    cells = []
    for case in spec.cases:
        for arm in spec.arms:
            cell = dict(
                caseId=case.id,
                armId=arm.id,
                sourceTrajectoryId=case.source_trajectory_id,
                sourceEventId=case.source_event_id,
                supported=False,
            )
            try:
                parent = service.db.get("trajectories", case.source_trajectory_id)
                source_experiment = service.db.get("experiments", parent["experimentId"])
                if source_experiment["workspaceId"] != spec.workspace_id:
                    raise ValueError("Source trajectory does not belong to workspace")
                prepared = await service.forks.prepare(concrete_fork(spec, case, arm.id))
                preview = prepared.preview()
                supported = (
                    spec.execution_spec.continuation == "single_turn"
                    or prepared.replay_support["supported"]
                )
                cell.update(
                    supported=supported,
                    reasonCode=None if supported else prepared.replay_support["reasonCode"],
                    reason=None if supported else prepared.replay_support["reason"],
                    inputHash=prepared.input_hash,
                    executionHash=prepared.execution_hash,
                    contextCharacters=preview["contextCharacters"],
                    replaySupport=prepared.replay_support,
                    replayPlanHash=prepared.replay_plan_hash,
                    replayEntryCount=len(prepared.replay_tape),
                    baseSeed=prepared.generation_parameters.get("seed"),
                )
                del prepared
            except ValueError as exc:
                cell.update(reasonCode="invalid_cell", reason=str(exc))
            cells.append(cell)
    return dict(
        specHash=spec_hash(spec),
        totalCases=len(spec.cases),
        totalArms=len(spec.arms),
        replicationCount=spec.replication_count,
        totalTrials=len(cells) * spec.replication_count,
        allSupported=all(c["supported"] for c in cells),
        cells=cells,
    )
