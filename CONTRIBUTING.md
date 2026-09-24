# Contributing to TraceLab

Keep changes focused and preserve existing research workspaces. Follow [AGENTS.md](AGENTS.md) for domain invariants and [architecture](docs/architecture.md) for module boundaries.

## Before opening a pull request

- Use `pnpm install --frozen-lockfile` and `uv sync --project backend --frozen`; commit intentional changes to their lockfiles and `src-tauri/Cargo.lock`.
- Add meaningful tests for behavior changes, including malformed inputs, partial failures, cancellation, and restart when relevant. Do not replace real integration behavior with a simulated UI result.
- Never change source logs, silently repair model output, invent scores, or claim restoration/replay that has not been verified. Retain raw evidence and provenance.
- Keep providers and formats independent. Classifiers and views consume canonical TraceLab events.
- Do not commit datasets, local workspaces, credentials, dependencies, generated Tauri schemas, compiled binaries, or app bundles. Small authored test fixtures and application icon assets are source files.
- Review the staged diff. Run `python3 scripts/check_repository.py` after staging; it checks the actual indexed blobs without printing detected secrets.

```sh
uv run --project backend ruff check backend tests scripts
uv run --project backend ruff format --check backend tests scripts
uv run --project backend pytest tests -q
pnpm test
pnpm build
cargo check --locked --manifest-path src-tauri/Cargo.toml
git diff --check
```

Report commands and outcomes in the pull request. Distinguish deterministic provider tests, live public-corpus checks, paid model execution, and visual inspection. Never claim CI has passed until its run has completed.

## CI and downloadable builds

The **CI** workflow runs on pull requests and pushes to `main`. It validates the source tree, workflows, Python lint/format/tests, and the TypeScript frontend. A dependent macOS ARM64 job checks Rust, reruns backend tests on macOS, bundles Python and Tauri with an ad-hoc signature, verifies that signature, and runs the packaged-runtime smoke test. After ZIP extraction it verifies the signature and runtime again. It archives the app with executable permissions, SHA-256 checksums, and build/commit metadata. Successful pushes and manual runs expose the archive under **Actions → CI → Artifacts** for 14 days. Pull requests validate packaging without publishing a downloadable artifact.

Builds are produced from the checked-out commit and committed lockfiles. Git stores source, never the resulting app. The macOS bundle is ad-hoc signed and unnotarized; it is a development artifact without an Apple-verified publisher identity. Apple distribution signing and notarization require a separate credential-backed release configuration. No automatic release publishing, installer for other platforms, or bit-for-bit reproducibility is claimed.

After downloading and extracting the Actions artifact, run `shasum -a 256 -c SHA256SUMS` alongside its ZIP to verify the download. Keep `BUILD.txt` with any reported packaging problem so the originating commit and tool versions are clear.

Workflow actions use immutable commit hashes, checkout does not retain credentials, the token has read-only contents access, jobs have timeouts, and superseded runs are cancelled. No model/HF secrets are supplied. Dependency updates arrive as Dependabot pull requests and must pass the same checks; they are not automatically merged. Public HF tests are a separate opt-in manual-workflow input.

Configure a `main` ruleset after the repository exists: block force pushes/deletion, require pull requests and the two CI checks, and require conversations to be resolved. CODEOWNERS identifies review ownership; it does not itself enforce approval. Repository/plan-dependent rules must be verified in GitHub rather than assumed from checked-in files.

Workflow references: [GitHub runner platforms](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), [Tauri CI](https://v2.tauri.app/distribute/pipelines/github/), [uv in Actions](https://docs.astral.sh/uv/guides/integration/github/).
