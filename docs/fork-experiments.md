# Fork experiments (PR2)

A `ForkExperiment` is an explicit design: cases × arms × replications. It is separate from the imported-log `Experiment` model. Execution does not establish task success and does not estimate treatment effects. No scorer or inferential statistics are introduced.

## Concrete design

A case binds one source trajectory and one concrete source event ID. Each case lists every experiment arm exactly once, with its own concrete interventions. Event IDs are never mapped by index, name, similarity or meaning across trajectories. Different fork points on the same source may be separate cases.

An arm has an ID, name and descriptive `control`/`treatment` role. The UI defaults to Control and Treatment, with empty interventions. A zero-intervention control is a real stochastic continuation, not the historical parent. Researchers can deliberately configure different models or generation parameters with existing interventions; the system preserves these differences and does not infer validity from an arm's role.

Limits: 1–200 cases, 1–8 arms, 1–100 replications, at most 2,000 total trials. Duplicate case IDs, arm IDs or case/arm bindings are rejected. Every source must belong to the specified workspace. Normal fork preparation validates the source point and every intervention target against its prefix.

## API and request

The namespace is **`forkExperiments.*`** because the existing `experiments.list` API must continue listing imported logs. Available operations: `preview`, `run`, `list`, `get`, `trials`, `resume`. Cancellation uses `jobs.cancel`.

Example request to `forkExperiments.preview` or `forkExperiments.run`:

```json
{
  "workspaceId": "ws_research",
  "name": "Remove evaluator hint",
  "arms": [
    {"id": "control", "name": "Control", "role": "control"},
    {"id": "remove_hint", "name": "Remove hint", "role": "treatment"}
  ],
  "cases": [
    {
      "id": "case_A",
      "sourceTrajectoryId": "traj_A",
      "sourceEventId": "traj_A:e184",
      "arms": [
        {"armId": "control", "interventions": []},
        {"armId": "remove_hint", "interventions": [
          {"type": "remove_event", "eventId": "traj_A:e141"}
        ]}
      ]
    }
  ],
  "executionSpec": {
    "continuation": "multi_step",
    "toolPolicy": "recorded_replay",
    "maxModelSteps": 8,
    "maxToolCalls": 32
  },
  "modelOverrides": {
    "provider": "openrouter",
    "model": "provider/model-id",
    "parameters": {"seed": 50, "max_tokens": 2048}
  },
  "replicationCount": 5,
  "schedulePolicy": "paired_interleaved_v1"
}
```

Use real IDs from the workspace. A second case must explicitly name its own fork point and intervention IDs. Credentials remain in configured provider environments; `modelOverrides` only accepts provider ID, model and parameters.

Preview validates every cell with `ForkRunner.prepare`, computes compact identities and discards heavy prepared contexts. It makes no model calls and creates no forks, experiments, trials, children or resolutions. Existing lazy parent ingestion may populate the local source cache. The response contains `allSupported`, counts, `specHash` and per-cell support/reason, input/execution hashes, context character count and replay plan identity/count.

Run repeats authoritative preflight. An unsupported cell returns `{started:false, preview:...}` before execution artifacts are persisted. The UI disables Run until all cells pass and submits `expectedSpecHash`; a mismatch raises “Experiment specification changed since preview.” A changed design requires a new experiment; there is no edit API, and existing concrete experiment Fork IDs cannot be overwritten through `forks.run`.

`specHash` hashes the canonical concrete design, including ordered case/arm IDs, bindings, execution configuration, base overrides and schedule policy. Generated Fork/Trial/experiment IDs, timestamps and child IDs are excluded. PR1's input/execution/replay hashes retain their meanings.

## Durable scheduling

One concrete Fork is persisted per case/arm. One ForkTrial is persisted per case/arm/replication. The complete matrix commits before a Job starts. Additive JSON tables `fork_experiments` and `fork_trials` retain specifications and lifecycle state; indexes cover workspace, experiment and linked child trajectory.

The exact schedule is:

1. Iterate replication indices starting at zero.
2. Within each replication, iterate cases in supplied order.
3. Rotate supplied arm order by `(case_position + replication_index) % arm_count`.
4. Persist monotonically increasing `scheduleOrdinal` and `schedulePolicy`.

`pairKey = caseId + ':r' + replicationIndex` is scoped to the ForkExperiment. All arms in that case/replication share it. Each trial and child retain case ID, arm ID, replication index, pair key, schedule ordinal and requested seed. Seeds use the effective prepared cell's base seed plus replication index. Explicit arm overrides remain visible; otherwise arms request the same seed. This is **paired requested seed**, not a guarantee of identical random draws or provider seed support.

Execution is serial, `Job.concurrency = 1`, through `ForkRunner.run_replication` and the existing Inspect lock. Shared Fork initialization/finalization preserves PR1 provenance. Only the current cell's PreparedFork is retained; it is reconstructed and its execution identity checked before each scheduled trial. No unbounded context cache or second model loop exists.

A child links back to its trial at creation, before provider execution. Partial events, tool resolutions and genuine raw records retain PR1 semantics. Generated calls still precede their results within a model output.

## Failures, cancellation and resume

- Trial `complete` means operational completion, including policy stops and configured bounds. It does not mean task success.
- Provider/execution failure marks that trial `error` and scheduling continues. A finished schedule with errors is `partial`; even all-provider-error schedules remain explicit trial results, rather than being hidden as a scheduler failure.
- `failed` is reserved for orchestration failure without meaningful completed work; an orchestration failure after finalized trials yields `partial`.
- Cancelling the existing Job cancels the active replication, preserves its child, marks the active trial `cancelled`, leaves unstarted trials `pending`, and marks the experiment `cancelled`. Completed artifacts are unchanged.
- Startup changes running experiments to `partial` and running trials to `interrupted`. Pending and complete trial states are retained. No model calls restart automatically.
- `forkExperiments.resume({id})` accepts partial/cancelled experiments with pending trials, validates the persisted concrete design again, checks preparation identities, and creates a new Job. Only pending trials execute. Error/interrupted/cancelled trials are never automatically retried. Job history is persisted.
- A case/arm Fork is complete only if all its trials complete operationally; infrastructure errors/interruption/cancellation mark it failed. Pending work remains visible.

Job progress counts finalized trials (`complete`, `error`, `cancelled`, `interrupted`) against the original total, including on resume. Logs contain case/arm/replication/status, not prompts or tool observations.

## UI and inspection

Fork Lab has Branches and Experiments views. The manual builder exposes arms, concrete cases, execution settings and provider/model/parameters. “Add selected event” reads the actual event object and copies its ID. It does not guess IDs. Review/edit concrete per-case JSON explicitly; automatic intervention matching is deliberately absent.

Preview displays supported cells and reasons, trial total and the configured maximum model-call count. No monetary estimate is invented. The result matrix links to paginated trial lists and ordinary child trajectories. Pair keys, requested seeds, errors and execution termination reasons remain visible. Lists are workspace-scoped; list/trial endpoints accept offset and limit (maximum 200). Detail includes descriptive case/arm/cell counts and reported call/token totals, not task metrics or treatment effects.

One aggregate “Experiment branch analysis” job reuses existing rule/statistical analysis and parent-child comparison functions after a scheduling run, including cancellation when the backend remains open. Existing comparisons avoid duplicate completed work on resume. Paid LLM detectors never rerun automatically. Analysis failure does not alter execution status; backend shutdown may prevent automatic analysis from starting.

## Boundary for PR3

`ForkTrial` and its child trajectory are durable inputs for a future ScoreRunner/ScoreResult. This PR introduces no scores, scorer editor, retries of failed trials, significance tests, confidence intervals, treatment effects, automatic alignment, live environments, parallel execution or distributed workers. Original historical source trajectories remain reference data.
