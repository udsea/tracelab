"""Serial durable scheduling over ForkRunner; no model/replay implementation here."""

import asyncio

from tracelab.experiments.models import ForkExperiment, ForkExperimentSpec, ForkTrial
from tracelab.experiments.preparation import concrete_fork, preflight, schedule
from tracelab.models.domain import Fork, Job, now

TERMINAL = {"complete", "error", "cancelled", "interrupted"}


class ExperimentRunner:
    def __init__(self, service):
        self.service = service
        self.db, self.jobs, self.forks = service.db, service.jobs, service.forks
        self.start_lock = asyncio.Lock()

    def trials(self, id):
        return [
            ForkTrial.model_validate(t)
            for t in self.db.list(
                "fork_trials",
                "experiment_id=?",
                [id],
                limit=2000,
                order="CAST(data->>'scheduleOrdinal' AS INTEGER)",
            )
        ]

    async def start(self, spec: ForkExperimentSpec, expected=None):
        async with self.start_lock:
            preview = await preflight(self.service, spec)
            if expected is not None and expected != preview["specHash"]:
                raise ValueError("Experiment specification changed since preview.")
            if not preview["allSupported"]:
                return {"started": False, "preview": preview}
            fork_experiment = ForkExperiment(**spec.wire(), spec_hash=preview["specHash"])
            cells = {(c["caseId"], c["armId"]): c for c in preview["cells"]}
            forks = {}
            for case in spec.cases:
                for arm in spec.arms:
                    fork = concrete_fork(spec, case, arm.id)
                    fork.metadata.update(
                        experimentId=fork_experiment.id,
                        caseId=case.id,
                        armId=arm.id,
                        preparationIdentity=cells[case.id, arm.id]["executionHash"],
                    )
                    forks[case.id, arm.id] = fork
            trials = []
            for ordinal, (case, arm, replication) in enumerate(schedule(spec)):
                seed = cells[case.id, arm.id]["baseSeed"]
                trials.append(
                    ForkTrial(
                        experiment_id=fork_experiment.id,
                        case_id=case.id,
                        arm_id=arm.id,
                        fork_id=forks[case.id, arm.id].id,
                        replication_index=replication,
                        pair_key=f"{case.id}:r{replication}",
                        schedule_ordinal=ordinal,
                        requested_seed=seed + replication if isinstance(seed, int) else None,
                        metadata={"schedulePolicy": spec.schedule_policy},
                    )
                )
            fork_experiment.fork_ids = [f.id for f in forks.values()]
            fork_experiment.trial_ids = [t.id for t in trials]
            fork_experiment.metadata.update(**self.forks.execution_provenance(), jobIds=[])
            fork_experiment.status = "running"
            # Commit the complete design/trial matrix before any job can execute.
            with self.db.lock:
                self.db.conn.execute("BEGIN")
                try:
                    self.db.put("fork_experiments", fork_experiment)
                    for fork in forks.values():
                        self.db.put("forks", fork)
                        for index, item in enumerate(fork.interventions):
                            self.db.put(
                                "interventions",
                                {"id": f"{fork.id}:{index}", "parentId": fork.id, **item.wire()},
                            )
                    for trial in trials:
                        self.db.put("fork_trials", trial)
                    self.db.conn.execute("COMMIT")
                except BaseException:
                    self.db.conn.execute("ROLLBACK")
                    raise
            return self.launch(fork_experiment)

    async def resume(self, id):
        async with self.start_lock:
            fork_experiment = ForkExperiment.model_validate(self.db.get("fork_experiments", id))
            if fork_experiment.status not in ("cancelled", "partial"):
                raise ValueError("Only cancelled or partial experiments can resume")
            if not any(t.status == "pending" for t in self.trials(id)):
                raise ValueError(
                    "No pending trials remain; failed or interrupted trials are not retried"
                )
            # Validate original concrete cells again without replacing any trial.
            preview = await preflight(self.service, fork_experiment)
            if not preview["allSupported"]:
                return {"started": False, "preview": preview}
            identities = {}
            for fid in fork_experiment.fork_ids:
                fork = self.db.get("forks", fid)
                identities[fork["metadata"]["caseId"], fork["metadata"]["armId"]] = fork[
                    "metadata"
                ]["preparationIdentity"]
            for cell in preview["cells"]:
                if cell["executionHash"] != identities[cell["caseId"], cell["armId"]]:
                    raise ValueError(
                        "Prepared source/configuration changed; create a new experiment"
                    )
            return self.launch(fork_experiment)

    def launch(self, fork_experiment):
        job = Job(
            kind="experiment",
            name=fork_experiment.name,
            total=len(fork_experiment.trial_ids),
            completed=sum(t.status in TERMINAL for t in self.trials(fork_experiment.id)),
            concurrency=1,
            metadata={"forkExperimentId": fork_experiment.id, **self.forks.execution_provenance()},
        )
        fork_experiment.status = "running"
        fork_experiment.job_id = job.id
        fork_experiment.metadata.setdefault("jobIds", []).append(job.id)
        self.db.put("fork_experiments", fork_experiment)
        result = self.jobs.start(job, lambda j: self.run(fork_experiment, j))
        return {"started": True, "experimentId": fork_experiment.id, "job": result}

    def finalize_forks(self, fork_experiment, only=None):
        trials = self.trials(fork_experiment.id)
        for fid in [only] if only else fork_experiment.fork_ids:
            own = [t for t in trials if t.fork_id == fid]
            fork = Fork.model_validate(self.db.get("forks", fid))
            bad = any(t.status in ("error", "interrupted", "cancelled") for t in own)
            if bad or all(t.status == "complete" for t in own):
                self.forks.finalize_execution(fork, bad)
            else:
                fork.status = "running" if fork_experiment.status == "running" else "configured"
                self.db.put("forks", fork)

    async def run(self, fork_experiment, job):
        active = None
        try:
            for trial in self.trials(fork_experiment.id):
                if trial.status != "pending":
                    continue
                active = trial
                trial.status, trial.started_at = "running", now()
                self.db.put("fork_trials", trial)
                label = f"Case {trial.case_id} · {trial.arm_id} · replication {trial.replication_index + 1}/{fork_experiment.replication_count}"
                self.jobs.save(job, label + " started")
                try:
                    fork = Fork.model_validate(self.db.get("forks", trial.fork_id))
                    prepared = await self.forks.prepare(fork)
                    if prepared.execution_hash != fork.metadata["preparationIdentity"]:
                        raise ValueError("Prepared source/configuration changed since preflight")
                    self.forks.initialize_execution(prepared, job)
                    trial.metadata["executionProvenance"] = {
                        k: fork.metadata.get(k)
                        for k in ("gitCommit", "traceLabVersion", "inspectVersion")
                    }
                    self.db.put("fork_trials", trial)

                    def created(child):
                        trial.child_trajectory_id = child.id
                        self.db.put("fork_trials", trial)

                    child = await self.forks.run_replication(
                        prepared,
                        trial.replication_index,
                        job,
                        child_metadata=dict(
                            executionProvenance=trial.metadata["executionProvenance"],
                            forkTrialId=trial.id,
                            forkExperimentId=fork_experiment.id,
                            experimentCaseId=trial.case_id,
                            experimentArmId=trial.arm_id,
                            replicationIndex=trial.replication_index,
                            pairKey=trial.pair_key,
                            scheduleOrdinal=trial.schedule_ordinal,
                            requestedSeed=trial.requested_seed,
                        ),
                        on_child_created=created,
                    )
                    trial.status = (
                        "error"
                        if child.status == "error"
                        else "cancelled"
                        if child.status == "cancelled"
                        else "complete"
                    )
                    trial.error = (
                        child.metadata.get(
                            "executionError",
                            child.metadata.get("terminationDetail", "Branch execution failed"),
                        )
                        if trial.status == "error"
                        else None
                    )
                    trial.metadata.update(
                        terminationReason=child.metadata.get("terminationReason"),
                        executionStatus=child.metadata.get("executionStatus"),
                    )
                    del prepared
                except asyncio.CancelledError:
                    trial.status = "cancelled"
                    raise
                except Exception as exc:
                    trial.status, trial.error = "error", str(exc)
                finally:
                    trial.completed_at = now()
                    self.db.put("fork_trials", trial)
                    job.completed = sum(
                        t.status in TERMINAL for t in self.trials(fork_experiment.id)
                    )
                    self.jobs.save(
                        job,
                        label
                        + f" {trial.status} · {trial.metadata.get('terminationReason') or ''}",
                    )
                active = None
                self.finalize_forks(fork_experiment, trial.fork_id)
            fork_experiment.status = (
                "complete"
                if all(t.status == "complete" for t in self.trials(fork_experiment.id))
                else "partial"
            )
        except asyncio.CancelledError:
            fork_experiment.status = "cancelled"
            raise
        except Exception as exc:
            fork_experiment.status = "partial" if job.completed else "failed"
            fork_experiment.metadata["orchestrationError"] = str(exc)
            if active and active.status == "running":
                active.status, active.error = "interrupted", str(exc)
                self.db.put("fork_trials", active)
            raise
        finally:
            self.finalize_forks(fork_experiment)
            self.db.put("fork_experiments", fork_experiment)
            try:
                from tracelab.analysis.branches import schedule_experiment_analysis

                analysis = schedule_experiment_analysis(self.service, fork_experiment)
                fork_experiment.metadata["analysisJobId"] = analysis["id"]
                self.db.put("fork_experiments", fork_experiment)
            except Exception as exc:
                self.jobs.save(job, f"Experiment branch analysis unavailable: {exc}")
