# Validation record

## 2026-09-25 — Fork experiments (PR2)

Based on merged PR #13 (`0aac3b9`). All execution continues through the existing ForkRunner replication primitive and Inspect lock. No paid model calls or fresh public downloads were used.

| Command | Observed result |
| --- | --- |
| `uv run --project backend pytest tests/test_fork_experiments.py -q` | 13 passed (final focused recovery check: 13.04 s) |
| `uv run --project backend pytest tests/test_fork_experiments.py tests/test_fork_replay.py -q` | 70 passed |
| `uv run --project backend pytest tests -q` | 199 passed, 3 opt-in public-corpus skips in final 77.20 s run |
| `uv run --project backend ruff check backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check backend tests scripts` | 105 files already formatted |
| `pnpm test` | 54 passed in 12 files |
| `pnpm build` | TypeScript/Vite passed; existing chunk advisory remains (application 541.93 kB, charts 556.60 kB before gzip) |
| `cargo check --locked --manifest-path src-tauri/Cargo.toml` | Passed after allowing locked dependency downloads |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | 4 passed, 0 failed |
| `python3 scripts/check_repository.py` | 263 indexed files, zero findings |
| `git diff --cached --check` | Passed |

Python used `UV_CACHE_DIR=/private/tmp/tracelab-uv-cache`; pnpm used the cached 10.30.3 CLI. The first Rust attempt could not resolve static.crates.io under network restrictions; the authorized retry passed. Early UI tests found an empty-builder guard bug (fixed) and required a stable accessible label on the concrete-case field (added). Node's existing local-storage warning remains nonfatal.

Deterministic backend acceptance covers a 2-case × 2-arm × 3-replication matrix, all trials persisted before the first run_replication call, exact rotated ordering, concrete source-specific IDs, paired requested seeds and explicit overrides, normal policy termination, isolated provider errors, concurrent experiment requests sharing serial Inspect execution, cancellation including immediate cancellation, restart reconciliation/child-link recovery, pending-only resume with a new Job, immutable concrete forks, all-cell preflight with zero artifacts on rejection, expected-spec hash checks, bounds, and aggregate cheap analysis with independent failures. The existing PR1 replay/presentation, comparison and one-off fork tests pass.

The 3-case × 2-arm × 5-replication fixture created six concrete Forks and 30 trials. An injected failure in the final trial yielded five 5/5 cells and one 4/5 cell, with 29 complete, one error and experiment status partial. No success/effect estimate was produced. Eight new frontend tests cover totals, preview gating/invalidation, concrete binding preservation, actual selected-event IDs, matrix/progress rendering, child navigation, existing job cancellation and valid resume visibility.

A separate 12-trial local provider-double run was closed and reopened. Raw inspection confirmed 11 complete/one error, persistent child links, schedule ordinals 0–11, paired keys and seeds 50/51/52. This is database/DOM verification, not a rebuilt native-app visual acceptance.

Cached pinned `budget_siphon_H` at event #69 was used for a real-source preview: one case, two arms (unmodified control and an explicit appended instruction), two replications, four proposed trials. Both cells were supported, each with 31 replay observations and the same replay-plan hash; input/execution hashes differed. Source-record hashes were unchanged and zero ForkExperiments/Forks/ForkTrials/Jobs were created. Spec hash: `c718a67cc8db360ed5c26c4a461563ba03a697e3162581068304f39b0f92251c`. This used the previously pinned HF corpus locally; it does not establish a two-independent-run matched corpus acceptance. No duplicate source was presented as another genuine run.

The builder uses explicit per-case JSON bindings and does not automatically map events. Maximum-size throughput, paid-provider experiments, native visual acceptance, scores, effects and distributed execution were not tested or claimed. See [fork experiments](fork-experiments.md) for API shape and lifecycle semantics. Hosted CI must be checked on the pushed commit separately.

## 2026-09-25 — Post-merge multi-call event ordering hotfix

Based on merged PR #12 (`b99211e`). All normalized events from one model generation now precede its resolved observations. Result parent edges still point to their corresponding calls. No replay policy, model context, frontend or native code changed.

| Command | Observed result |
| --- | --- |
| `uv run --project backend pytest tests/test_fork_replay.py -q` | 57 passed in 18.15 s |
| `uv run --project backend pytest tests -q` | 186 passed, 3 opt-in corpus skips in 99.45 s |
| `uv run --project backend ruff check backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check backend tests scripts` | 99 files already formatted |
| `pnpm test` | 46 passed in 11 files |
| `pnpm build` | TypeScript/Vite passed; existing >500 kB chunk advisory remains |
| `cargo check --locked --manifest-path src-tauri/Cargo.toml` | Passed |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | 4 passed, 0 failed |

Python used `UV_CACHE_DIR=/private/tmp/tracelab-uv-cache`; pnpm used the cached 10.30.3 CLI. Focused cases verify normalized mixed-block order, two-call replay success, partial mismatch without another generation, bounds preserving excess calls, mixed replay/stub results, explicit result parents, ToolResolution event IDs, counters and parent/source immutability. The broad suite includes existing comparison/divergence and cheap post-fork analysis tests.

Two isolated local provider-double branches were persisted, their services closed and reopened, and their raw canonical rows inspected. Full resolution was `call A, call B, result A, result B`; partial resolution was `call A, call B, result A`. Result A pointed to call A and result B to call B, with matching ToolResolution IDs and recorded-replay origins. These were raw database checks, not native visual acceptance. No paid calls or remote-corpus reruns were needed. Previously persisted trajectories are not rewritten by this fix. Hosted CI is reported separately after checking the pushed commit.

This records executable checks, not scientific results. Synthetic/provider-double outputs are not promoted to research evidence. Updated 2026-09-24 for the focused UX pass; the earlier semantic presentation, filtered navigation and concurrent desktop IPC record follows unchanged.

## UX pass (2026-09-24)

| Command | Observed result |
| --- | --- |
| `pnpm test` | 40 passed in 10 files |
| `pnpm build` | TypeScript and Vite passed. The main chunk grew from 490.07 kB to 525.04 kB before gzip (161.58 kB gzip) and now also exceeds the >500 kB advisory; the ECharts chunk is unchanged at 556.60 kB |
| `uv run --project backend pytest tests -q` | 129 passed, 3 skipped (opt-in public corpus reads) |
| `uv run --project backend ruff check backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check backend tests scripts` | 94 files already formatted |
| `pnpm audit --audit-level moderate` | No known vulnerabilities found |
| `uv run --project backend python scripts/smoke_bundle.py backend/.venv/bin/tracelab-backend` | Passed against the development entry point (6 runs, 2 fork branches, populated restart, no model calls). Not a packaged-app run |
| `cargo check --locked --manifest-path src-tauri/Cargo.toml` | Passed |
| `python3 scripts/check_repository.py` | 243 indexed files, 0 findings |
| `git diff --cached --check` | Passed |

No Rust or Tauri files changed; `cargo test` and `cargo fmt --check` were not rerun. Hosted CI was not observed for this change.

Frontend tests cover the five-section Analysis navigation, the Overview hiding raw measurements by default, derivation wording without probability language, one-moment-per-lane prioritization, hidden empty inspector channels, per-lane window collapsing, the fork dialog targeting and prefilling the selected event, generation-parameter serialization and rejection, line diffs, search/command shortcut labels, command-palette navigation (go to event, switch workspace, out-of-range rejection) and Run Outline visibility by section. Backend tests cover the sample's matched pair, rule/statistical signals, synthetic fork (runner storage, no provider, no Inspect log, unscored branches), branch comparison, completed jobs, and `forks.preview` matching the run reconstruction without exposing credential values or persisting a fork.

Manual walkthrough in the browser development build at 1280×800, dark and light themes, on a fresh data directory: Welcome, opening the sample (about 9 s), Explorer, Analysis Overview/Signals/Compare/Internals/Notes, the fork dialog with a replacement diff and preview, Fork Lab, Comparisons (suggested pairs and preselected conditions) and the command palette. A copy of the isolated `budget_siphon_H` acceptance database was reopened: 309 recorded / 221 research / 88 runtime / 14 opaque events, initial selection #2, #70 shown as redacted reasoning with raw payload lazy, Reasoning keeps #70 and Runtime shows the nearest #69 notice. The original acceptance database was not modified.

## Earlier record: semantic presentation and concurrent IPC

### 2026-09-25 — Multi-step recorded tool replay

| Command | Observed result |
| --- | --- |
| `uv run --project backend pytest tests -q` | 183 passed, 3 opt-in public-corpus skips in 55.18 s |
| `uv run --project backend pytest tests/test_fork_replay.py -q` | 54 passed in 8.20 s after final canonical assistant-output fixture verification |
| `uv run --project backend ruff check backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check backend tests scripts` | 99 files already formatted |
| `pnpm test` | 46 passed in 11 files |
| `pnpm build` | TypeScript/Vite passed; existing >500 kB chunk advisory remains (application 530.85 kB, charts 556.60 kB before gzip) |
| `cargo check --locked --manifest-path src-tauri/Cargo.toml` | Passed |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | 4 passed, 0 failed |
| `TRACELAB_REMOTE_TESTS=1 uv run --project backend pytest tests/test_remote_corpus.py -q -s` | 3 passed in 47.49 s; public read-only corpus, no model calls |
| `python3 scripts/check_repository.py` | 251 indexed files, zero findings |
| `git diff --cached --check` | Passed |

Python used `UV_CACHE_DIR=/private/tmp/tracelab-uv-cache`; pnpm 10.30.3 used its locally cached CLI. The first frontend invocation accidentally discovered a separate `.claude/worktrees/ux-pass` checkout and failed with duplicate-React hook errors. Discovery is now explicitly scoped to `src/**/*.test.{ts,tsx}`; this checkout's full suite passes. The other worktree was not modified. Node's existing local-storage warning remains nonfatal.

Coverage includes legacy execution defaults, rejected combinations, exact canonical arguments, sequential matching with no search-ahead, repeated identical calls, multi-call partial resolution, exhaustion/mismatch, bounds, exact stubs and permanent replay disablement, unknown task outcomes, provider errors, cancellation, token accounting, provenance/hashes, missing/dynamic/lossy schemas (including copied ancestor records), malformed generated calls, unsupported observations, parent/raw immutability, pure previews and persisted resolution retrieval. UI tests exercise mode defaults, request serialization, bounds, capability blocking, plan summaries, source links, replay/stub badges and honest wording.

Production Inspect execution was exercised with its local mock model, not a replacement execution UI. A three-generation branch received `alpha` and `2 passed`, wrote one native `.eval`, and retained generated call IDs. The native transcript contains three model events and zero executed tool/sandbox events. A generated shell command that would create a sentinel file was persisted as unmatched; no file appeared. A real cancellation test caught Inspect swallowing cancellation and returning an empty log list; the adapter now owns outer cancellation, joins Inspect cleanup, preserves the resolved prefix and marks the child cancelled. A subsequent test passed with no third model call.

The ordinary RPC `forks.run` job path completed and scheduled only the existing cheap branch-analysis job. A complete service close/reopen retained the fork execution spec, child events, replay origin, ToolResolution rows and explicit raw replay records. Existing single-reply execution and synthetic-demo tests remain in the broad suite.

### Real corpus preparation only

Both cached and freshly imported `budget_siphon_H` from the pinned HF commit below were checked without model invocation. At fork event **#69**, explicit `ModelEvent.tools` recover four unchanged definitions: `shell`, `read_file`, `write_file`, `list_dir`. The strict tape contains **31 observations**, beginning with call **#72** and result **#74**. Catalog hash: `4ae5b90e0b1b92a2979b49f224507f6736eb2131e6bde86413945523ce5b9eb0`; plan hash: `2887f9fa6d8ddac962e82e8ed01d815fe32aacb5ce8d5d9d0eeb94af8073e488`.

Preparation reports support. It created zero forks, children or resolution rows; raw source hashes stayed unchanged. All 14 opaque reasoning placeholders remain protected. The ignored local report is `.tracelab/replay-acceptance/report.json`; corpus bytes and local application databases are not committed. Public tests also rechecked lazy metadata/sample loading and offline pinning. Hugging Face retried one interrupted range response through its existing transport policy; all three tests passed.

This establishes replay preparation for the real run and multi-step execution with deterministic local models. It does **not** establish compatibility with every provider's historical reasoning format, a paid continuation, restored environment, task score, causal effect or packaged-native UI acceptance. No paid model calls were made. Unsupported catalogs/observations fail closed. Full semantics and the PR2 boundary are in [fork execution](fork-execution.md). Hosted CI status must be checked on the eventual PR; local results alone do not establish it.

## 2026-09-24 — Presentation/IPC commands (historical)

| Command | Observed result |
| --- | --- |
| `pnpm test` | 18 passed in 5 files |
| `pnpm build` | TypeScript and Vite passed; ECharts chunk 556.60 kB before gzip retains the existing >500 kB advisory |
| `uv run --project backend pytest tests -q` | 127 passed, 3 skipped; the skipped tests are explicitly opt-in public corpus reads |
| `uv run --project backend ruff check backend tests scripts` | All checks passed |
| `uv run --project backend ruff format --check backend tests scripts` | 94 files already formatted |
| `cargo test --locked --manifest-path src-tauri/Cargo.toml` | 4 passed, 0 failed; local fake Python sidecar exercises the production Rust transport |
| `cargo check --locked --manifest-path src-tauri/Cargo.toml` | Passed |
| `cargo fmt --check --manifest-path src-tauri/Cargo.toml` | Passed after installing the official rustfmt toolchain component |
| `pnpm audit --audit-level moderate` | No known vulnerabilities found |
| `TRACELAB_REMOTE_TESTS=1 uv run --project backend pytest tests/test_remote_corpus.py -q -s` | 3 passed in 36.08 s; pinned public reads, no model calls |
| `go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 -color` | Passed |
| `python3 scripts/check_repository.py` | 232 indexed files, 0 findings |
| `git diff --cached --check` | Passed |

Python commands used `UV_CACHE_DIR=/private/tmp/tracelab-uv-cache`. pnpm 10.30.3 was invoked through its locally cached CLI. The DOM tests isolate persistent UI storage; this local Node installation emitted a `--localstorage-file` warning without test failures.

## Regression coverage

- Explicit semantic/runtime/opaque classification, known Inspect lifecycle records, `sample_init`, meaningful sandbox actions, and task-state bookkeeping versus tool configuration.
- Source-driven redacted/encrypted/summary/signature handling, signed readable text, absence of a base64-only heuristic, raw preservation and lazy disclosure.
- Old cached event projection, invalidation on canonical writes, exact shared list/locate predicates, mode/range/query combinations, nearest-event ties and empty views. Canonical #70 maps to reasoning row 11 in the authored regression fixture, independently of canonical index.
- Real classifier, segmentation and outline formatting paths with provider doubles: no ciphertext or runtime narrative reaches their prompts. Fork context preserves original opaque blocks; explicit edited reasoning takes precedence in a child.
- DOM/hook tests cover Reasoning → All, normal row clicks, count refreshes, explicit jumps, cancelled/stale location responses, initial research selection, Runtime access, opaque placeholders and per-event raw inspection. Verification is not screenshot-only.
- Rust tests prove health overtakes a slow request; timeout preserves PID and an independent running request; late responses cannot satisfy another waiter; crash closes all pending calls promptly; IDs increase across restart; cancellation and malformed lines do not poison later replies.
- Python concurrency tests hold a real DuckDB read inside a blocking UDF while separate reads and writes complete. Blocked route handlers leave health and job polling responsive. First presentation generation permits job progress and cached event reads, and retries when a concurrent canonical update invalidates its snapshot. Transaction tests verify committed visibility and rollback.
- Existing format/provider, streaming/offline, synthetic Inspect demo, classifier provenance, fork, annotation, comparison and analysis-signal tests remain in the full backend suite. No paid model calls were made for this change.

## Real Gemini acceptance

The target is `budget_siphon_H` from `aisa-group/instrumental-choices-agent-traces`, pinned to commit `c5c77cd662316e609515dcdee5131788dd724258`:

```text
inspect_logs/openrouter_google_gemini-3.1-pro-preview_exacto/repeat_01/
2026-04-26T08-28-50+00-00_budget-siphon-task_hv8xPLk3QXDSGp5gdG98dC.eval
```

The selected file is 7,598,009 bytes. Corpus data and local acceptance scripts/reports are ignored under `.tracelab/presentation-acceptance/`; no source logs or builds enter Git. The native application database was left untouched; acceptance used an isolated database.

Observed final presentation:

| Metric | Value |
| --- | --- |
| Recorded events | 309 |
| Research events | 221 |
| Semantic events | 207 |
| Runtime records | 88 |
| Opaque reasoning placeholders | 14 |
| Recorded model-call IDs / boundaries | 37 / 37 |
| Deterministic outline nodes | 14 |

All 37 source reasoning blocks are explicitly `redacted: true`; 23 include readable summaries, and 14 have no readable summary. Event #70 contains a 144-character redacted state payload and no summary. TraceLab displays **Redacted reasoning**, retains the exact payload under raw inspection, and excludes it from semantic/classifier text. It does not assert encryption solely from appearance.

| Filter with canonical #70 selected | Filtered row offset | Visible event | Exact |
| --- | --- | --- | --- |
| All events | 53 | #70 | yes |
| Reasoning | 5 | #70 | yes |
| Tools | 10 | #72 | no |
| Errors | 0 | #228 | no |
| Runtime | 16 | #69 | no |

`span_begin`, `span_end`, `sample_init` and duplicated task-output bookkeeping move to Runtime. Concrete sandbox commands/file writes and tool configuration remain research observations. No task success or behavioral interpretation was inferred from these records.

Both fresh pinned ingestion and old cached normalization were exercised. Local verification compared canonical event rows and source-record hashes before/after projection, checked every redacted payload against semantic/classifier formatting, and reopened the projected trajectory with source-provider access disabled. All checks passed. The browser UI displayed the real run, qualified reasoning placeholders, counts and raw-disclosure controls; concurrent user interaction prevented a reliable complete manual filter-switch sequence. The exact #70 sequence is established by API and automated frontend tests. This was not verification of a newly packaged native app.

The separate lazy remote Inspect regression transferred zero file-content bytes for repository listing, 185,750 bytes for header/sample summaries and 251,286 bytes cumulatively after opening one sample of a 382,358-byte file. These measurements belong to the smaller quota-boost fixture, not the 7.6 MB budget-siphon file. Its cached restart and explicit offline pin checks passed too.

## Scope limits

- Unmarked encoded reasoning cannot be reliably detected; no text-appearance heuristic claims it can.
- Historical classifier/outline results and their provenance remain unchanged. Rerun analysis to apply the new research-event input semantics.
- Opaque state can be preserved/replayed by compatible existing backends; it is not interpreted as readable reasoning or a model-internal measurement.
- Read concurrency does not promise hard latency bounds. Writes remain serialized and resource contention is possible. A request timeout does not cancel its Python operation; inspect Activity before retrying an action that starts work.
- The IPC process tests run on Unix with local Python. No new Windows/Linux packaged acceptance was performed.
- No new paid-provider run, million-event performance result, signing/notarization claim or rebuilt native artifact is established here. CI now includes the Rust tests, but local checks do not establish hosted CI success.

Earlier real-run/live-provider evidence and the outstanding native ATIF corpus gap remain recorded in [analysis](analysis.md). They are historical evidence, not reruns performed for this patch.
