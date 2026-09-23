# Universal sources

Use **Add trajectory source** (Cmd/Ctrl+O). Local files and directories remain available. The Hugging Face tab accepts repository IDs, repository/tree/blob/resolve URLs, and `hf://` references. Select dataset, model, or space and a revision. HTTP accepts a stable file URL or a `manifest.json` directory listing.

Connecting to Hugging Face resolves the revision to a commit SHA and lists metadata. It does not clone a repository or download its files. Select files and choose **Detect selected formats** to inspect bounded prefixes (Inspect detection also validates its native header). **Open remote** imports selected files only. Inspect indexes sample summaries and reads individual samples on selection; JSONL and structured JSON streams normalize progressively in background jobs.

| Format | Recognition and normalization |
| --- | --- |
| Inspect | Native header validation; official `read_eval_log`, sample summaries, and selected-sample reader through a public fsspec bridge |
| ATIF | `ATIF-` schema marker; streamed steps, embedded agents, delegation references, continuations, metrics, and raw metadata |
| ATOF | Versioned scope/mark records; scope starts/ends and parent UUIDs form a graph; opaque custom data remains raw |
| HF Session Trace | Session header and message envelopes; reasoning, calls/results, timestamps, and metadata; supported Codex/Pi/Claude message envelopes |
| OTLP JSON | Resource/scope spans, trace/span/parent IDs, GenAI attributes, errors and timings; messages are children of spans |
| Generic | Bounded structural inference, reviewed editable paths, reusable schema fingerprints |

Generic imports never call a model automatically. Review the mapping and choose **Approve mapping**. Paths use `$`, simple dotted field paths, and `[*]`; event fields are relative to one event. **Send shown preview & suggest mapping** explicitly sends only the displayed bounded schema/sample to the chosen provider. The suggested mapping still requires review. Matching structural fingerprints reuse approved profiles. Heterogeneous JSONL records and nested run envelopes remain distinguishable through raw records and run/agent scopes within the selected stream.

**Detect run bundle in this directory** proposes agent streams, score/configuration files, and artifact directories. Review the proposal to import them as one run with independent agent scopes. This uses the same source-provider listing for local, HF, and HTTP manifests. An HTTP manifest has a `files` array of `{ "path": "agent.jsonl", "sizeBytes": 1234, "etag": "..." }` entries; an optional `url` can override the relative path. Arbitrary HTML indexes are not scraped.

## Cache and provenance

Click the trajectory's format/provider badge to inspect its source URI, SHA, path, ETag/checksum, cached bytes, import status, capabilities, and index errors. **Check revision** offers a separate new import when a branch moves. Existing experiments remain pinned.

Remote raw metadata, 64 KiB ranges, and fully pinned files live in a disposable cache next to the research database. Normalized events remain in the existing DuckDB tables. The default raw-cache limit is 20 GiB with LRU eviction; change it in Settings. Pins are protected and may exceed the limit. Clearing raw cached data does not delete normalized events, annotations, classifiers, or provenance.

**Pin offline** downloads the selected source file; for Inspect this includes the selected `.eval` file, making its unopened samples available too. For run bundles it pins agent streams, score/config files, and listed artifacts. It never snapshots the repository. Partial raw ranges and already normalized events remain usable during outages. Index failures preserve completed events and offer retry. Analysis waits for complete indexing so it cannot silently classify an incomplete run.

HTTP servers need stable content lengths. If a server ignores byte ranges, TraceLab streams only the selected file to disk as a compatibility fallback. HTTP URLs containing credentials, query strings, or fragments are rejected; use stable URLs. Hugging Face authentication uses the standard local `huggingface_hub` login or `HF_TOKEN`; TraceLab does not persist the token in its database or workspace.

## Capabilities and boundaries

Classifiers, segmentation, local search, annotations, and comparisons consume canonical events regardless of source. Agent timeline lanes and inspector parent links consume normalized graph relationships. No benchmark adapter or format-specific classifier is involved.

Reading a trace does not establish replay capability. Context forks are enabled only for Inspect integration after context reconstruction validates. Other formats retain analysis capability but have no execution adapter. Checkpoint/environment restoration and exact replay remain disabled. Unknown source fields are retained in raw event/header metadata and the original immutable source reference. External ATIF references remain references; TraceLab does not silently fetch arbitrary linked files or claim their environments are restored.

JSONL is streamed with a 32 MiB per-record safety limit. ATIF/OTLP use `ijson`; a single step/span is the parsing unit. Very large individual records and multi-million-event display targets have not been benchmarked. Raw session formats change independently; unsupported records are retained as `other`, rather than fabricated into chat messages. Generic inference is structural and may need an edited mapping for unfamiliar schemas.

## Validation and compatibility sources

Offline tests cover HF listing without file reads, measured ranges, pins, restarts, revision identities, remote format normalization, scope/span/agent relationships, mapping review/reuse, partial-batch failures, run bundles, and existing classifier/segmentation integration. No model API is called.

```sh
uv run --project backend pytest tests -q
# Explicit public network test; no model calls:
TRACELAB_REMOTE_TESTS=1 uv run --project backend pytest tests/test_remote_corpus.py -q -s
```

The public test pins `aisa-group/instrumental-choices-agent-traces` at `c5c77cd662316e609515dcdee5131788dd724258`, selects one Inspect log and one STS file, checks byte counts, lazy samples, restart, and offline pinning. Remaining format transport tests use a measured mock HF filesystem instead of downloading corpora.

Format references: [Inspect Log API](https://inspect.aisi.org.uk/reference/inspect_ai.log.html), [HF filesystem](https://huggingface.co/docs/huggingface_hub/en/guides/hf_file_system), [HF Session Trace format](https://huggingface.co/docs/hub/session-traces-format), [Harbor ATIF RFC](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md), [NVIDIA ATOF](https://docs.nvidia.com/nemo/relay/latest/reference/atof-event-format), [OTLP specification](https://opentelemetry.io/docs/specs/otlp/).
