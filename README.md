# TraceLab

A local desktop research IDE for long-horizon AI-agent trajectories. Inspect executes evaluations and owns the native `.eval` format; TraceLab adds navigation, behavioural analysis, interventions, and comparison.

## Run

Requirements: Python 3.12+, `uv`, Node 22+, and pnpm 10. Desktop development also requires Rust and the [Tauri 2 platform prerequisites](https://v2.tauri.app/start/prerequisites/).

```sh
pnpm install --frozen-lockfile
uv sync --project backend --frozen
pnpm dev
```

Open **http://127.0.0.1:1420**. Choose **Explore a sample workspace** for six explicitly synthetic, 487-event trajectories in genuine Inspect `.eval` files. No model calls are made on startup or when opening the sample.

If pnpm is not installed, commands can be prefixed with `npm exec --yes --package=pnpm@10.30.3 --` (for example, `npm exec --yes --package=pnpm@10.30.3 -- pnpm dev`).

For the native application:

```sh
pnpm desktop
```

To build a self-contained application with a bundled Python runtime:

```sh
pnpm desktop:build
```

On macOS, the result is `src-tauri/target/release/bundle/macos/TraceLab.app`. The build uses PyInstaller for the Python resource bundle, then Tauri. The app bundle is ad-hoc signed for integrity. Apple Developer ID signing and notarization are not configured. The supplied bundle target is macOS; Windows/Linux packaging has not been validated.

GitHub Actions builds and smoke-tests the macOS ARM64 app from source after the CI checks pass. Download the ZIP, checksum, and build metadata from a successful **Actions → CI → Artifacts** run. Build outputs are ignored by Git and are never committed. See [contribution and CI practices](CONTRIBUTING.md) and [security guidance](SECURITY.md).

On first launch, macOS may require explicit approval because this development build is not notarized. After verifying the archive checksum, use **System Settings → Privacy & Security → Open Anyway** if offered for TraceLab. Do not disable Gatekeeper globally. If macOS says the app is damaged, check `codesign --verify --deep --strict /path/to/TraceLab.app` and report the build commit and error; a runtime smoke-test pass alone does not establish bundle integrity.

## Research workflow

1. Choose **Add trajectory source** for a local file/directory, Hugging Face repository/file, or HTTP URL. Inspect indexes headers and sample summaries lazily; ATIF, ATOF, HF Session Trace, OTLP JSON, and reviewed generic streams normalize into the same trajectory model. See [source formats, remote caching, and offline pinning](docs/sources.md).
2. Select a trajectory. Browse compact/expanded events, tool/reasoning/error filters, and phases. Full event and raw Inspect records load on demand.
3. Customize a classifier template. Choose an event, rolling window, or trajectory scope; select the model, target trajectories/experiment/condition, and concurrency. **Save & run** executes a real job.
4. Inspect signals on the timeline. Click a point or signal card for the rationale, linked evidence, exact prompt, raw attempts, and reproducibility record.
5. Add manual annotations or request optional LLM segmentation. Phase labels and boundaries can be edited; episodes are limited to one nested level.
6. Fork a model-context prefix, apply interventions, and execute replications. Open children as ordinary trajectories and compare them with their parent.
7. Compare experiment/condition groups. Click aggregates to inspect contributing trajectories; unknown outcomes and classifier coverage stay explicit.

### Providers

The settings screen configures a base URL, model default, and **environment variable name**, never an API key. Start the application from a shell with the appropriate key set (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or `ANTHROPIC_API_KEY`). Restart after changing environment variables. A Finder-launched application may not inherit shell environment variables.

OpenAI-compatible providers use `/chat/completions` with a strict JSON schema. Anthropic uses a forced structured tool response. Local vLLM and other compatible servers can use a configurable endpoint; the server must implement structured output. Provider errors surface in the job rather than silently falling back to another model or output format.

Running a classifier, segmentation, or fork sends its selected context to the configured provider. Optional schema assistance sends its displayed bounded preview only after an explicit action. Remote sources retrieve selected raw data; analysis and its persisted results remain local. Credentials are never stored in DuckDB, renderer state, or source control.

### Fork fidelity and scope

**Context-only replay is implemented and executes through Inspect.** It reconstructs the normalized recorded prefix, applies validated interventions, and generates **one model continuation per replication** in a new Inspect evaluation. Its native log, exact context, parameters, seed when requested, model, versions, lineage, and source IDs are persisted.

This mode does **not** resume the original tool implementations, solver/agent scaffold, filesystem, running processes, external APIs, or scorer. It does not recreate an entire tool-using task from a log. A completed model call is an **unscored** trajectory, not a successful task. Token usage for a branch describes its continuation call, while its displayed event count includes the replayed prefix.

- Pending/orphan tool calls are rejected. Remove both a call and its result, or replace the result.
- Unsupported multimodal context, compacted prefixes, and explicit agent branches are rejected rather than silently reconstructed incorrectly.
- Signed reasoning is retained when available; editing signed reasoning is rejected. Provider/model changes can still make historical reasoning incompatible.
- **Checkpoint restoration is disabled.** Checkpoint markers can be inspected, but this adapter has no verified public mechanism for restoring an arbitrary captured sandbox into an independent intervention branch. There is no fabricated restoration mode.
- Differences are heuristic event alignment, not semantic alignment or causal evidence. The intervention point is separate from the first subsequent recorded difference.

### Evidence semantics

- Inspect execution status does not establish task success. Imported trajectories remain `unknown` unless they have an execution error; native scorer values are preserved independently. Synthetic examples have explicitly authored outcomes.
- Invalid classifier JSON is retried exactly once. Failed windows retain both attempts and a visible error. There is no JSON repair, label coercion, or invented evidence.
- Evidence IDs must belong to the exact input window. Cache identity includes the entire definition, endpoint/provider, model, exact prompt/input, schema, and generation parameters.
- Timeline, filters, and aggregate views use the most recent run for each trajectory/classifier. Historical results and run snapshots remain stored. Aggregates average within each trajectory first; long trajectories do not get extra group weight simply for having more windows.
- LLM segmentation uses bounded semantic event summaries, including tool outcomes, agent identity, recorded parents and timing; its complete input prompt is retained. A validated segmentation covers the entire trajectory without phase overlaps/gaps. Failed regeneration preserves existing phases.
- Original `.eval` files are never written. Changed files are indexed as separate versions; unopened trajectories refuse a changed source until it is re-imported. Loaded normalized snapshots and analysis remain intact.

## Storage and architecture

```text
React + TypeScript + TanStack Query
            ↓ typed application JSON
Tauri commands (Rust process ownership)
            ↓ JSON-lines over local stdin/stdout
Python: source provider → format importer → canonical trajectory → analysis/forks → DuckDB
```

The browser development server forwards the same protocol to Python through a Vite middleware. It binds to loopback, checks the request origin and content type, and does not expose a Python HTTP server. The desktop app uses Rust IPC directly.

Desktop storage uses Tauri's application-local directory. Browser development defaults to `.tracelab/` in this checkout (`TRACELAB_DATA_DIR` overrides it). Workspace sources, analyses, annotations, caches, and fork logs stay there. Development and native desktop storage are intentionally separate. Run one app instance per database.

Inspect-specific imports and version handling are confined to `backend/tracelab/inspect_adapter/`. Backend models are Pydantic; the renderer receives application types, never Inspect objects. ECharts is the only chart library. Zustand persists lightweight navigation/theme state; TanStack Query owns backend data.

The event list is virtualized and requests 100 compact summaries per visible page. Raw content/provenance is lazy. Trajectory browsing and text search use database-side filtering and pagination. Text search reports unopened trajectories and offers background indexing. Million-event and 10,000-trajectory performance targets have **not** been benchmarked; this build does not claim measured capacity at those sizes.

## Keyboard

| Shortcut | Action |
| --- | --- |
| Cmd/Ctrl + O | Add trajectory source |
| Cmd/Ctrl + K | Command palette |
| / | Search workspace |
| J / K | Next / previous event |
| A | Annotate selected event |
| F | Fork selected event |
| Escape | Close dialog |

## Validation

```sh
pnpm build
pnpm test
uv run --project backend pytest tests -q
uv run --project backend ruff check backend tests
cargo check --manifest-path src-tauri/Cargo.toml
# After building the macOS bundle:
python3 scripts/smoke_bundle.py
```

Tests cover native `.eval` lazy import, immutable source logs, source-version changes, normalization, cache identity, bounded classifier concurrency, cancellation, strict schema/evidence validation, provenance, latest-run aggregate semantics, search/filtering, segmentation, intervention validation, heuristic divergence, restart recovery, and real Inspect execution/log writing with its local mock model. The bundle smoke check creates an isolated synthetic workspace, verifies paginated events and linked classifier evidence, compares conditions, and reopens the populated database in a second packaged process. Provider HTTP contracts use deterministic local test doubles. Paid model endpoints are not exercised by the tests.

The [analysis guide](docs/analysis.md) covers the shared signal model, run outline, timeline scales, detector semantics, artifact hooks and real-run acceptance limits.

See [architecture notes](docs/architecture.md) and [validation record](docs/validation.md).
