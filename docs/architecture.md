# Implementation boundaries

`src/app/App.tsx` owns the desktop layout and shortcuts. Components under `components/trajectory/`, `timeline/`, and `classifier/` render virtualized events, ECharts lanes, and evidence. Feature modules implement import, classifier editing, forks, comparisons, and structured filtering. `lib/api.ts` chooses Rust IPC in Tauri and the local Vite bridge in development.

`src-tauri/src/main.rs` owns one Python sidecar per app, serializes JSON-lines commands, enforces response-ID matching and timeouts, and terminates its child on exit. Python redirects all third-party stdout to stderr so model/evaluation progress cannot corrupt the IPC channel. Long-running work returns a persisted job immediately; the renderer polls activity.

`api/service.py` is an explicit command allowlist. Services are separated into ingestion, classifiers, segmentation, forks, comparison, and storage. Commands never accept SQL, Python code, or shell commands. User-supplied tool-call content is data and is never executed on the host.

`storage/database.py` keeps document JSON alongside indexed relational keys. One locked DuckDB connection serializes writes. Batch writes use transactions. Original Inspect events are preserved in `source_records`; normalized events refer to those records. `current_classifier_results` is a view over the latest observed run for each trajectory/classifier, leaving old result rows immutable.

`inspect_adapter/backend.py` uses `list_eval_logs`, `read_eval_log(..., header_only=True)`, `read_eval_log_sample_summaries`, and `read_eval_log_sample(..., resolve_attachments=True)`. Full samples are loaded only on demand. `normalize.py` turns reasoning, tool calls, tool results, model messages, scores, errors, checkpoints, and other events into application events; unknown records are retained. The installed compatibility baseline is Inspect AI 0.3.268.

`sources/` owns locations and byte access: local files, immutable HF commit references, HTTP/manifest access, seekable cached ranges, LRU eviction, and offline pins. Its disposable SQLite cache catalog is separate from the unchanged research DuckDB schema. `importers/` detects and normalizes formats into application events; the Inspect importer stays under `inspect_adapter/` and uses a registered public fsspec bridge to the official reader. `ingestion/universal.py` persists metadata first and streams batches of normalized events, preserving partial results on cancellation or errors. `sources/concurrency.py` joins cancelled worker threads before their iterator or cache closes. The analysis stack receives only canonical trajectories and events.

`classifiers/runner.py` supplies exact events and IDs, validates the output JSON schema and Pydantic model, rejects out-of-window evidence, retries malformed output once, and records raw attempts. Workers consume bounded windows without spawning one task per window. Provider transport failures are recorded without implicit SDK retries.

`forks/context.py` applies edits to copies and validates the tool-call/result protocol. `inspect_adapter/replay.py` constructs an Inspect task using the reconstructed context, a configured model, and `generate(tool_calls="none")`. The original task code and environment are not imported or executed. `forks/runner.py` serializes Inspect eval calls, saves each replication as a trajectory, retains partial/error branches, and stores native logs separately from sources.

At startup, jobs and fork trajectories left running by an interrupted backend are marked failed/error with an explanation. Classifier outputs already completed remain available. Cancellation awaits in-flight workers and never promotes an incomplete result to a completed job.

## Deliberate limits

- The context-only fork is a model continuation, not arbitrary long-horizon agent restoration. Original tool runtime/scorer binding is a future adapter capability.
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
