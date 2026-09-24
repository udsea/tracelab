# Fork execution: single replies and recorded observations

A fork is a context-only intervention branch, initially **unscored**. Its execution result does not establish task success or failure. Parent trajectories, normalized parent events and raw source records remain unchanged.

## Supported execution specifications

`Fork.executionSpec` is optional on existing records/requests. Its default preserves single-reply execution. The application model uses camelCase at the API boundary and snake_case in Python.

| Mode | Tool policy | Environment | Scoring | Unmatched policy |
| --- | --- | --- | --- | --- |
| `single_turn` (default) | `disabled` | `none` | `none` | `fail`; no stubs |
| `multi_step` | `recorded_replay` | `none` | `none` | `fail` or `stub` |

Other combinations are rejected, including live/simulated tools, restored environments and scorer reruns. Both supported modes retain `fidelity=context_only`. Bounds default to 8 model steps and 32 generated tool calls; accepted ranges are 1–100 and 1–1000 respectively. They are experiment bounds, not a claim about context capacity or cost.

**Single reply:** reconstruct the edited context; disable tools; make one generation through the existing Inspect solver. Existing requests need no migration.

**Multi-step recorded replay:** reconstruct the edited context; expose explicit recorded tool schemas; make a bounded sequence of generations. Each generated action can receive only the next exact recorded observation or an explicitly configured synthetic stub. **Tools are never executed. Environment state is not restored. A replayed observation is not evidence that its value would still hold after the intervention.** This is continuation under recorded observations, not exact counterfactual replay.

## Preparation and tool catalog

`forks/preparation.py` produces a typed `PreparedFork`, shared by `forks.preview` and execution. It includes the parent/source event, edited prefix, reconstructed messages, provider/model, generation parameters, execution specification, catalog, ordered tape and hashes. CPU-heavy preparation uses the existing joined-worker helper. Preview never calls a model, persists experiment objects or consumes observations. Loading an unopened parent may still populate the existing local ingestion cache.

`inspect_adapter/tool_catalog.py` reads explicit `ModelEvent.tools` from source records attached to the relevant future model events. It never infers a schema from arguments, loads source task code or installs executable tools. The current public Inspect `ToolInfo` representation is validated before execution. Schemas whose non-null constraints would be dropped by Inspect are rejected. JSON Schema's default allowance of additional properties is made explicit when absent because Inspect otherwise defaults it to false. Null optional fields in native Inspect serialization are treated as absent.

Every relevant future catalog must agree on names, descriptions and schemas. Reordering definitions does not change identity. Missing definitions, provider-specific execution options and changes fail closed; step-wise dynamic catalogs are not implemented. Tools with no description may use an empty description, but an explicit object parameter schema is mandatory.

Capability reason codes include `tool_schema_unavailable`, `dynamic_tool_catalog_unsupported`, `no_future_tool_calls`, `ambiguous_tool_result`, `unsupported_tool_result` and `context_reconstruction_unavailable`. Unsupported multi-step requests are rejected before creating a fork/job through the RPC route.

## Replay tape and matching

The tape is built from the original parent, **strictly after the selected fork event**, irrespective of which earlier event an intervention edits. Maps of recorded call IDs to calls/results are built once. Missing, duplicate, orphaned, reversed or inconsistent identities fail preparation; an uncertain action is never skipped to build an apparently compatible tape. Entries retain source event indices/IDs, source-record references, exact arguments, results/errors and hashes. The tape is a tuple of frozen entry models; resolver cursors are independent for each replication, and returned provider messages copy observations.

`canonical_tool_arguments` is the sole argument canonicalizer. It recursively sorts object keys, preserves array order and uses stable JSON for scalars. Top-level strings containing JSON objects/arrays are parsed as structured arguments; other strings and nested string values retain exact contents. It does not trim commands, normalize paths, lowercase text or collapse spaces. Non-finite JSON values are rejected.

`strict_sequential_exact_v1` compares the generated tool name and canonical arguments to the current tape entry only. It never searches ahead. A match consumes that entry once. Repeated identical source calls therefore yield their distinct observations in order.

Multiple generated calls are persisted and resolved in generated order. If A matches and B differs, the child contains A, its replayed result and B without an invented result; no next generation occurs. Any remaining calls emitted in that same output are preserved as unresolved observations. `toolCalls` counts all generated calls, including unresolved calls and calls emitted beyond the resolution limit. The bound prevents resolving calls beyond the limit; it cannot prevent a provider from emitting a larger batch in one output.

Only text and explicit text-block observations are currently representable. Structured recorded tool errors retain their error type/message. A null successful body accompanying an error becomes empty content plus the same error, not a successful result. Arbitrary JSON objects, binary/multimodal results and unrepresentable errors fail closed rather than being stringified.

## Exact synthetic stubs

A `ToolStub` contains `id`, `toolName`, exact `arguments`, `result` and optional structured `error`. Duplicate IDs or duplicate exact match keys are rejected. No wildcard, name-only, regex or semantic matching exists.

On a mismatch, `unmatchedToolPolicy=stub` may use an exact stub. That observation is marked `origin=stub`, `synthetic=true` and `replayState=diverged_by_stub`. **Recorded replay never resumes after the first stub.** Subsequent calls can use other exact stubs (including repeated use of a configured stub) or terminate. Stub records carry no matched source IDs. Source observations remain available only for provenance/debugging.

## Inspect execution and cancellation

`inspect_adapter/replay.py` uses the public `Task`, `eval_async`, `solver`, `Model.generate`, `ToolInfo` and chat-message APIs. One evaluation encompasses all generations in one replication. The custom solver passes schemas to `Model.generate`; it never installs `Tool`/`ToolDef`, invokes a tool executor or restores the original solver, sandbox, task or scorer. Recorded tool result messages answer the **generated child call ID**, never the parent's ID.

The existing process-wide Inspect lock covers the entire replication and cancellation cleanup. Replications are sequential. The adapter owns the outer evaluation task so Inspect's internal cancellation handling cannot turn cancellation into an empty-log infrastructure error. It cancels and joins Inspect before releasing the lock. Partial model events and resolutions are persisted after each completed generation/resolution. Cancellation does not discard them. Log directories are retained even when an interrupted evaluation cannot return a log object.

The existing replication seed rule is unchanged: explicit seed, seed+1, seed+2. Each replication starts with an independent cursor and the same prepared tape. There are no implicit retries or paid detector reruns.

## Status and accounting

| Termination | Child task status | Execution status | Fork status if all replications terminate this way |
| --- | --- | --- | --- |
| `assistant_completed` | `unknown` | `complete` | `complete` |
| `unmatched_tool_call`, `replay_tape_exhausted`, `unsupported_tool_result` | `unknown` | `policy_terminated` | `complete` |
| `max_model_steps`, `max_tool_calls` | `unknown` | `bounded` | `complete` |
| `model_error`, `tool_resolution_error` | `error` | `error` | `failed` |
| `cancelled` | `cancelled` | `cancelled` | existing `failed` fork state, with cancellation reason |

A generation invocation is one model step, independently of emitted event count. Continuation token usage is aggregated from reported usage only; copied prefix usage is excluded. If any generation lacks a usage field, that aggregate remains unknown. Scores stay empty. Policy termination is an observed experiment outcome, not task failure or causal proof. Intervention point and first behavioral divergence remain separate in existing comparison views.

## Persistence and provenance

`tool_resolutions` follows the existing additive JSON-table pattern and has a trajectory index. `forks.resolutions` retrieves up to the maximum supported 1,000 resolutions for a child. Rows hold generated call/result event IDs, source links or stub identity, model step, argument hash, policy, ordinal and timestamp; they do not duplicate result bodies.

The child contains ordinary canonical events. Generated blocks share `modelCallId` and carry `forkId`, `branchGenerated`, `modelStep` and `executionMode`. Provider output/source data remains genuine Inspect data; opaque reasoning passes through the existing presentation layer. Synthetic replay source records explicitly say `type=tracelab_tool_replay`, origin and matched source/stub identity. They do not masquerade as executed tool records. Control state lives in execution metadata rather than semantic narrative events.

Child metadata includes the execution specification, generation parameters, accounting, cursor, termination, catalog/plan/execution hashes and explicit `environmentRestored=false`, `toolExecution=false`, `toolsRestored=false`, `scoring=none`. The provenance note reads: “Recorded tool outputs were reused without restoring or executing the source environment.” Original records and exact used observations remain inspectable after restart.

- `inputHash` retains its prior meaning: the effective reconstructed model context.
- `replayPlanHash` covers policy version, catalog hash and ordered source call/result event IDs, tool names, argument hashes and result/error hashes.
- `executionHash` covers input hash, provider ID, model, generation parameters, execution specification, catalog/plan identity and stub hashes. Replication-specific seeds produce replication-specific hashes. API key values are never hashed or persisted.

## UI and PR2 boundary

Fork Lab defaults to **Single reply**. **Multi-step recorded replay** exposes bounds, the exact-stub option, capability reasons and a compact replay plan without result bodies. Run is disabled while its current replay preview is pending or unsupported. Results display **RECORDED REPLAY** or **STUBBED**, with source links for recorded results. Child summaries distinguish assistant completion, policy stops, bounds, errors and stub divergence. Existing trajectory inspection, annotation, comparison and cheap post-fork analysis remain available.

`ForkRunner.run_replication(prepared, replication_index, job)` is the single-replication primitive. PR2 can orchestrate it later. This PR does not add batch experiments, parallel branches, scorers, monitor evaluations, simulated/live tools, environment reconstruction or checkpoint restoration.

Public API references: [Inspect model generation](https://inspect.aisi.org.uk/reference/inspect_ai.model.html), [custom solvers](https://inspect.aisi.org.uk/solvers.html). Executed evidence and the pinned real-corpus result are in [validation](validation.md).
