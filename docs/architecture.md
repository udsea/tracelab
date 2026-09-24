# Implementation boundaries

`src/app/App.tsx` owns the desktop layout and shortcuts. Components under `components/trajectory/`, `timeline/`, and `classifier/` render virtualized events, ECharts lanes, and evidence. Feature modules implement import, classifier editing, forks, comparisons, and structured filtering. `lib/api.ts` chooses Rust IPC in Tauri and the local Vite bridge in development.

`src-tauri/src/main.rs` owns one Python sidecar per app. Only JSON-lines writes hold the process mutex. `ipc.rs` runs one stdout reader and routes replies to per-request channels using process-lifetime monotonic IDs. A request timeout or cancelled caller removes its waiter without stopping Python; late replies are discarded. EOF/read failure closes all pending channels immediately. Intentional app exit closes stdin and retains the three-second wait/kill fallback. Python redirects all third-party stdout to stderr so model/evaluation progress cannot corrupt the IPC channel. Long-running work returns a persisted job immediately; the renderer polls activity.

`api/service.py` is an explicit command allowlist. Services are separated into ingestion, classifiers, segmentation, forks, comparison, and storage. Commands never accept SQL, Python code, or shell commands. User-supplied tool-call content is data and is never executed on the host.

`storage/database.py` keeps document JSON alongside indexed relational keys. One locked DuckDB connection serializes writes. Batch writes use transactions. Independent thread-local `cursor()` connections execute reads against committed snapshots without the writer lock; slow trajectory/search/detail/comparison handlers and job polling run in worker threads. Reader connections are closed after active reads drain. The presentation cache computes outside the write lock, checks per-trajectory in-memory revisions before publishing, and retries a concurrently changed snapshot. Cached reads bypass another trajectory's projection build. Original Inspect events are preserved in `source_records`; normalized events refer to those records. `current_classifier_results` is a view over the latest observed run for each trajectory/classifier, leaving old result rows immutable.

`inspect_adapter/backend.py` uses `list_eval_logs`, `read_eval_log(..., header_only=True)`, `read_eval_log_sample_summaries`, and `read_eval_log_sample(..., resolve_attachments=True)`. Full samples are loaded only on demand. `normalize.py` turns reasoning, tool calls, tool results, model messages, scores, errors, checkpoints, and other events into application events; unknown records are retained. The installed compatibility baseline is Inspect AI 0.3.268.

`sources/` owns locations and byte access: local files, immutable HF commit references, HTTP/manifest access, seekable cached ranges, LRU eviction, and offline pins. Its disposable SQLite cache catalog is separate from the unchanged research DuckDB schema. `importers/` detects and normalizes formats into application events; the Inspect importer stays under `inspect_adapter/` and uses a registered public fsspec bridge to the official reader. `ingestion/universal.py` persists metadata first and streams batches of normalized events, preserving partial results on cancellation or errors. `sources/concurrency.py` joins cancelled worker threads before their iterator or cache closes. The analysis stack receives only canonical trajectories and events.

`classifiers/runner.py` supplies exact events and IDs, validates the output JSON schema and Pydantic model, rejects out-of-window evidence, retries malformed output once, and records raw attempts. Workers consume bounded windows without spawning one task per window. Provider transport failures are recorded without implicit SDK retries.

`forks/context.py` applies edits to copies and validates the tool-call/result protocol. `forks/preparation.py` provides the typed, shared preview/execution input. `forks/replay.py` implements exact sequential recorded-observation matching and permanent replay disablement after a synthetic stub. `forks/execution.py` persists generated events, resolution provenance and accounting. `inspect_adapter/replay.py` uses one Inspect evaluation per replication: either the existing `generate(tool_calls="none")` single reply or a custom solver calling public `Model.generate` with schema-only `ToolInfo` definitions. No original tool implementations, task code or sandbox are loaded. `forks/runner.py` retains the Inspect execution lock for the entire replication and cancellation cleanup. See [fork execution](fork-execution.md).

`experiments/` orchestrates the existing `ForkRunner.run_replication` primitive. ForkExperiment and ForkTrial are separate from imported Experiment records. All concrete case/arm forks and paired trials are persisted before the experiment job starts. The `forkExperiments.*` API preserves the existing imported-log `experiments.list` namespace. Preflight discards heavy preparation objects; execution prepares one scheduled cell at a time and checks its identity. Startup marks active experiments partial and trials interrupted; resume schedules only pending records. One aggregate analysis job reuses existing cheap detectors and branch comparisons. See [fork experiments](fork-experiments.md).

At startup, jobs and fork trajectories left running by an interrupted backend are marked failed/error with an explanation. Classifier outputs already completed remain available. Cancellation awaits in-flight workers and never promotes an incomplete result to a completed job.

Presentation classification and filtered navigation are described in [analysis](analysis.md). Canonical indices, filtered row offsets and model-call coordinates remain distinct. The additive `event_presentations` table is disposable; canonical events and `source_records` remain retrievable.

## Deliberate limits

- Context-only continuations can reuse exact recorded observations; they do not restore or execute tools/environments. Live tool runtime and scoring remain future capabilities.
- Checkpoint events are not sufficient evidence that a filesystem can be restored. Restoration stays unavailable.
- Outcome interpretation is scorer-dependent. No generic mapping from an Inspect `success` execution to task success is applied.
- `source_records` retain the fields exposed by the supported Inspect public parser. Compatibility with future unknown log schema versions is not assumed.
- ECharts timelines load compact markers for the selected trajectory; the transcript DOM remains virtualized. No million-event benchmark result is claimed.
- Open in Inspect starts a loopback viewer for the containing log directory and displays the target sample ID; a precise sample deep link is not claimed.

## Primary references

- [Inspect log reading and sample summaries](https://inspect.aisi.org.uk/eval-logs.html)
- [Inspect model API](https://inspect.aisi.org.uk/reference/inspect_ai.model.html)
- [Inspect checkpoint guarantees and limitations](https://inspect.aisi.org.uk/checkpointing.html)
- [Tauri commands](https://v2.tauri.app/develop/calling-rust/)

- [DuckDB thread-local cursors](https://duckdb.org/docs/current/guides/python/multiple_threads)
