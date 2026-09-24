# Validation record

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

### Local commands and results

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
