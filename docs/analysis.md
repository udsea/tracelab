# Analysis and real-run visualization

TraceLab derives semantic summaries, a run outline, coordinates, relationships and analysis signals from canonical events. These additions do not replace source ingestion, Inspect execution, classifier records or legacy segments.

## Navigation

The outline combines existing segments with deterministic activity episodes, recurring activities and recorded relationship moments. Optional **Interpret outline with LLM** sends semantic event summaries, tool outcomes, agent identities, parents, timing and errors to the explicitly selected provider. Output must cite supplied event IDs. Interpretations can overlap; they need not partition the run. Legacy phase editing remains available. Deterministic overview results and model interpretations are cached locally.

**Events**, **Elapsed time** and **Model calls** share event selection and range navigation. Untimed events occupy a labeled ordinal gutter, never invented timestamps. When generation boundaries are unavailable, the model-call scale explicitly uses an assistant-message proxy. **Previous range** (shown once a range has been focused) restores navigation after opening detail; **Reset** shows the full run. The **View** menu holds density controls: zoom around the selection, **Expand**, **Signals only**, **All lanes**, runtime visibility and individual toggles for lanes that have data. Ctrl + scroll zooms and dragging pans; every gesture also has a button. Full-run activity uses aggregated bins; close views expose individual events. The event list and outline are virtualized. Agent activity is binned at low zoom; relationship pages contain at most 200 selectable edges.

Recorded parents, explicit sender/recipient envelopes and shared artifact references provide distinct relationship types. A parent does not prove communication. Shared artifacts do not establish transfer direction. An envelope may describe both endpoints in one recorded event; TraceLab does not invent a separate receiving event. Unknown agent identity stays unknown.

## Event presentation and raw preservation

Canonical event indices identify recorded events, including framework records. The derived presentation model is independent of canonical event type:

| Class | Meaning | Default visibility |
| --- | --- | --- |
| `semantic` | Readable behavior, tools, observed environment actions, scores, errors and checkpoints | All events and applicable filters |
| `runtime` | Known framework envelopes/lifecycle records and uninterpreted `other` records | Runtime filter; optional runtime timeline lane |
| `opaque` | Explicitly unreadable reasoning state | Compact qualified placeholder in All events and Reasoning |

**All events** means research events (`semantic + opaque`). Headers report research counts; the trajectory count tooltip distinguishes recorded, runtime and opaque counts. Outline statistics and default rule/statistical/contrastive distributions use research events. Classifier windows count research events while retaining canonical boundary indices and exact input event IDs; ranges can bridge omitted runtime records. Rule/statistical definitions can explicitly set `includeRuntime: true`. Timeline coordinates retain every recorded index for navigation, but default activity lanes omit runtime records and separate **Opaque reasoning** from readable **Reasoning**. Recorded relationships remain structural evidence.

`reasoningVisibility` is `plaintext`, `summary`, `encrypted`, `redacted` or `opaque`. Explicit content-block redaction/encryption/visibility fields take precedence; readable summaries are labeled as summaries. A signature accompanying readable text does not make the text opaque. Signature-only state is opaque. There is no base64 appearance detector. Unmarked encoded text cannot be reliably classified by this implementation.

New Inspect normalization retains exact content blocks and source records while making unreadable reasoning content null. Older canonical rows are untouched: a disposable, versioned `event_presentations` table derives safe UI/search projections on demand. Writing canonical events invalidates their projection. Inspect sandbox `exec`, `read_file` and `write_file` records with concrete commands/paths remain meaningful environment observations; a bare `sandbox` lifecycle placeholder does not establish an environment effect. `sample_init` and span envelopes remain recorded and explicitly runtime. Unknown records are preserved without invented behavioral meaning.

List responses use SQL-bounded previews. Ordinary event detail excludes raw provider blocks; **Show raw payload** / **Open raw source record** lazily calls `events.raw`. Disclosure is specific to the selected event. Internal replay still receives preserved source blocks, so opaque state can be replayed by the existing compatible backend without interpreting it as prose. Explicit branch replacements take precedence over their historical source block in presentation and replay. Parent events are never edited.

Semantic summaries, optional LLM outline interpretation, phase segmentation, classifier formatting and local text search omit opaque payloads. Opaque existence is represented by visibility metadata/an unavailable-reasoning summary. Runtime narrative content is excluded from default analysis. Existing historical classifier/outline results and raw provenance are retained; rerun them to obtain results with the new input semantics.

### Canonical indices and filtered row offsets

`events.list` and `events.locate` share one parameterized predicate for trajectory, mode, optional canonical range and text query. `events.locate` returns `{offset, exact, eventIndex, nearestEventIndex}`. `offset` is a zero-based row in that filtered view, not a canonical event index. Missing selections resolve to the nearest visible canonical index (ties choose the lower index); empty views return null offsets. Filter changes preserve the canonical selection and explain when the nearest row is shown. Initial opening selects the first research event if canonical zero is runtime.

The virtualized list navigates only on trajectory/filter/range changes and explicit jump/focus requests. It does not scroll in response to ordinary row selection or a count refresh after navigation completes. Cancelled/stale location responses cannot scroll a newer view. Explicit jumps to runtime events retain the selected inspector event even if the default list shows its nearest research neighbor; the Runtime filter exposes it.

Inspect model output blocks safely share a `modelCallId` derived from their source-record ID and selected output choice. Older cached blocks can recover that ID only when the source record, message identity and recorded generation usage establish the group. Other sources keep the existing recorded boundary or explicitly labeled assistant-message proxy. This does not invent a general Turn UI or unsupported generation boundaries.

## Analysis workspace

Analysis has five sections: **Overview**, **Signals** (Semantic / LLM, Rules, Statistical, Environment), **Compare**, **Internals** (multi-agent graph, imported internal signals) and **Notes**. Detector configuration stays one click away under Signals.

The Overview is derived in the renderer from the compact `analysis.signals` summaries; it never loads prompts, raw outputs or full evidence, and it makes no model call. Signals are grouped by detector and lane. Numeric lanes with at least two scores are summarized in their own units: early level (median of the first three windows), peak and its range, final window, first rise (the first window at least halfway from the early level to the peak, reported only when the peak rises that far above the early level), largest change between consecutive measurements and the number of elevated intervals. Headlines are descriptive (“Starts near 0.12, rises around #190–209 and peaks at 0.81”) and never convert scores into probabilities or behavioural conclusions. Rule and other point signals report matches; completed rules without matches are listed separately as not evidence of absence. Charts are inline SVG capped at 120 points. Important moments take one moment per detector lane before filling up to eight, so one busy detector cannot crowd out the others. The full measurement list stays behind **Show all measurements**.

The inspector lists only evidence channels with a measurement covering the selected event, one row per lane (overlapping rolling windows collapse to the one centred nearest the event). A single help control explains black, gray and white box channels.

## Shared signals

`AnalysisSignal` carries a trajectory/range, source type, evidence channel, score or label, evidence IDs, optional artifact reference and provenance. Existing `ClassifierResult` and annotations project into this model. Rules, statistics, environment observations, fork markers and imported internal measurements use the same lanes and inspector. Rolling results occupy their entire receptive interval. Scores are not universally probabilities: entropy is in bits and robust spikes may exceed one.

List APIs return compact signal summaries. The signal inspector loads full provenance and paginates evidence. Detector input manifests store exact event IDs and hashes once; detailed provenance resolves the manifest. Used classifier definitions and all edited rule/statistical definitions receive new version IDs. Prior definitions and results remain addressable.

Built-in rules cover evaluator-related argument access, evaluation-language mentions, successful explicit infrastructure writes, narrowly established claim/action contradictions, metadata-marked sensitive access and repeated tool calls. Infrastructure modification requires a successful structured outcome. Shell text mentioning an edit is insufficient. A completed rule with no matches is displayed as `no_matches`, not interpreted as absence of the underlying behavior.

Statistics use rolling categorical total-variation shifts, repetition fraction, tool entropy, action novelty, error fraction and median/MAD spikes. Unknown measurements are excluded from numeric baselines. These are configurable research heuristics, not validated behavioral ground truth.

Evaluation Awareness is a suite of separate evidence channels. The editable semantic template distinguishes evaluation inference from ordinary verification and requires confidence, observability, evidence, counterevidence and alternative explanations. Lower-level misrepresentation/withholding/concealment templates do not establish deception. Capability suppression belongs in matched control/treatment comparison, not a unary deception score.

## Comparison and intervention

Pair manually, by sample/task, or by a metadata field. Ambiguous automatic matches require manual selection. Compare outcomes, token/duration metrics, tools, event types, shared signal means and rule match counts. A zero rule count requires completed execution; an unmeasured detector remains missing. Signal means summarize emitted measurements and are not calibrated cross-detector scores. The existing heuristic alignment distinguishes the intervention point from subsequent divergence.

Signals expose capability-gated context forks before, at, or after their interval. A peak action uses a recorded peak index only; otherwise it says “signal start.” Successful forks schedule a separate cheap rule/statistical comparison job. Analysis failure does not change the fork outcome. Existing LLM results can be compared, but paid detectors are never silently rerun on branches. These are **observed branch comparisons**, not causal proof.

## Internal measurements

`ArtifactRef` and `ModelInternalSource` associate external Parquet/Zarr/NPZ/safetensors/JSON/custom artifacts with a trajectory. Tensors stay outside DuckDB. The Internal Signals screen can import local Parquet scalar exports with explicit event-index and score columns. The importer validates all rows before persisting references/signals, records a checksum, and currently accepts at most 100,000 scalar rows. No TransformerLens, NNsight or other model instrumentation is installed.

## Acceptance evidence and limits

Local acceptance data lives under ignored `.tracelab/dev-corpus/`, not Git. The local inventory and acceptance reports preserve source paths and SHA-256 checksums. Research repositories were read-only.

- Real Inspect runs from `collusion-monitoring`: 1,008 events / 179 tool calls; 813 events / 123 tool calls; a 133-event Case-B worker run. Deterministic outline, coordinates, rules, statistics, annotations, persistence and source immutability were checked. Case-B is a two-worker setup and was not relabeled as three agents.
- A public Astropy coding run (`astropy__astropy-12907`) normalizes to 180 events with seven recorded identities: Planner, Navigator, Editor, Executor and three named inner assistants. It contains 28 explicit message envelopes among the four outer roles. Generic mapping review explicitly assigns `$.agent_id`; initial setup records have no agent identity. Local corpus preparation extracts literal log headers and keeps original line offsets and the source checksum. It does not infer timestamps or receiving events. Source: [MAST human-labeled corpus](https://huggingface.co/datasets/Christmas1224/MAST-Data/blob/cb2807dbb5180c81195fe707cc6821a6f17c72cb/MAD_human_labelled_dataset.json), record 1. This is a prepared real trace, not evidence of native support for that benchmark's text-log wrapper.
- A public flat OTel span export was re-enveloped locally as OTLP JSON, retaining raw attributes, span IDs, parents and timestamps. It normalizes to 330 events. Source: [llmmas-otel baseline](https://github.com/vagabondboffin/llmmas-otel/blob/c777e4e070cab38a1707dcc18412c2ad303e5e58/out/demo%20for%20all%20samples/traces_baseline_r01.json). It contains two identified agents, not three.
- The explicitly authorized live acceptance used OpenRouter `anthropic/claude-sonnet-4.6`: one 20-event detector window and one context-only continuation (900/400 output-token limits). The first fork attempt failed before generation because Inspect required OpenAI SDK >=3.1; the dependency was corrected and the fork succeeded. Original source checksums remained unchanged. No environment restoration or causal claim is made.
- A synthetic scalar `probe_scores.parquet` is associated with the real Inspect trajectory for forward-compatibility testing. It is explicitly labeled synthetic and is not an actual model probe.

A native real ATIF trace with subagents remains a corpus acceptance gap. Synthetic graph/importer regression tests do not satisfy that requirement. Whole-run paid LLM outline/detector analysis and a live child LLM rerun were not performed. Million-event capacity and every multi-agent framework are not claimed. Current desktop packaging and signing remain governed by CI; local web verification is not packaged-native verification.
