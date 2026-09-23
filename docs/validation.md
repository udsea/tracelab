# Validation record

This file records executable checks, not scientific results. Synthetic examples and mock model outputs are never promoted to research evidence.

## Checks

- `pnpm build`: TypeScript strict type checking and Vite production build pass. Vite reports an advisory for the ECharts chunk exceeding 500 kB before compression.
- `pnpm test`: 4 tests pass for missing-value display and event/phase navigation resets.
- `uv run --project backend pytest tests -q`: 61 tests pass; two public network tests skip by default. Coverage includes source providers, range caching/offline pins, revision identities, remote-format normalization, ATIF delegation, ATOF scopes, OTLP trees, generic mapping review/reuse, run bundles, partial-stream failures/retry, unchanged analysis integration, repository policy rejection tests, and the existing Inspect/classifier/fork/comparison tests.
- `TRACELAB_REMOTE_TESTS=1 uv run --project backend pytest tests/test_remote_corpus.py -q -s`: both pass against the pinned public HF corpus documented in [sources](sources.md). Repository listing transfers zero file-content bytes. For a 382,358-byte `.eval`, headers plus eight sample summaries transfer 185,750 bytes; opening one selected sample uses 316,822 bytes total in the final run (sample ordering varies). Restart uses the local index; after pinning, an unopened sample loads with remote range/metadata reads disabled. The other public test imports STS JSONL. Counts measure file-content payloads, excluding metadata HTTP/TLS overhead.
- `uv run --project backend ruff check backend tests`: passes.
- Repository preparation: `ruff check backend tests scripts`, `ruff format --check backend tests scripts`, local `actionlint` v1.7.7, staged whitespace checks, and `scripts/check_repository.py` pass. The policy checks 193 indexed source/assets files with zero findings; no ignored files remain tracked. Local build bundles and generated Tauri schemas are excluded. The first hosted CI run found an additional ShellCheck redirect-style issue (ShellCheck was unavailable locally); the workflow now groups its build-metadata writes. A successful complete hosted build must still be verified.
- GitHub repository controls: private visibility, commit-pinned Actions requirement, read-only workflow tokens, no workflow PR approvals, dependency vulnerability alerts/automated security fixes, and merged-branch cleanup are enabled. GitHub refused private-repository branch protection with HTTP 403 because this account requires Pro for that feature. The repository remains private; no plan upgrade or visibility change was made.
- Inspect fork integration uses the public `mockllm` model with deterministic outputs, while running the actual evaluation and native `.eval` writer. It validates two replications, independent seeds, lineage, preserved parent data, and unscored child outcomes.
- `cargo check --manifest-path src-tauri/Cargo.toml` and the Tauri release app build pass on macOS arm64. `cargo fmt` was unavailable because this toolchain lacks the rustfmt component.
- `python3 scripts/smoke_bundle.py` passes against the rebuilt packaged runtime: six native Inspect trajectories, 487 events each, paginated events, 98 classifier results per trajectory, linked evidence, two condition groups, streamed ATIF import, and a second-process restart with persisted data. It verifies `CFBundleIconFile=icon.icns` and its bundled resource. It makes no model calls.
- After explicit launch approval, native visual checks verified the Add Source dialog, HF connection controls, metadata-only file browser, imported eight-sample Inspect experiment, a 125-event remote trajectory in the existing IDE, timeline, inspector, and provenance panel with SHA/checksum/cache/capabilities. Pin Offline completed and the panel showed all 373.4 KiB pinned. Browser automation was unavailable and concurrent user interaction interrupted some native actions; the entire 21-step workflow was not independently exercised through UI. Offline restart and analysis integration are established by automated tests, not a paid-model UI run. The feature pack's light theme and generic mapping dialog have not received visual verification.

## Not established by these checks

- Quality or validity of the classifier template prompts.
- Compatibility of a particular remote provider/model with every structured-output or reasoning-history option.
- Full agent/task continuation with original tool implementations.
- Checkpoint/environment restoration.
- The 10,000-trajectory / 1,000,000-event performance targets.
- Distribution signing/notarization or cross-platform packaged installers.

Use the README commands to reproduce the checks. Paid providers require explicit configuration and are not called during validation.
