# TraceLab

TraceLab is a local research IDE for trajectories, not an evaluation dashboard.

- Keep Inspect imports inside `backend/tracelab/inspect_adapter/`.
- Treat source logs as immutable. Use the public Inspect log API.
- Preserve unmapped source fields as metadata. Do not infer task success from execution success.
- Every derived result retains exact inputs, definition, provider configuration, raw output, and time.
- Never label a fork checkpoint-restored without a verified restoration implementation.
- No remote model calls in tests; use deterministic provider doubles, local HTTP fixtures, and Inspect's local mock model. Public read-only corpus tests must be opt-in and use pinned revisions.
- Frontend data flows through TanStack Query and typed RPC models; Zustand holds UI state only.
- Keep event lists virtualized and raw event data lazy.
- Validate with `pnpm build`, `pnpm test`, `uv run --project backend pytest tests -q`,
  `uv run --project backend ruff check backend tests`, and `cargo check --manifest-path src-tauri/Cargo.toml`.

Provider credentials are read from environment variables. Do not persist API keys or place them in the frontend.

- Commit source and lockfiles only. Build outputs, generated Tauri schemas, datasets, caches, and app bundles belong outside Git; distributable development builds come from CI artifacts.
- Before publishing, run `python3 scripts/check_repository.py` against the staged index. Never log suspected secret values.
- Pin GitHub Actions to full commit hashes, use least-privilege permissions and frozen dependency installs, and preserve the packaged-runtime smoke gate before artifact upload.
- Read `CONTRIBUTING.md` and `SECURITY.md` for review and release practices. Do not claim remote CI, signing, or branch protection exists without verifying it.
