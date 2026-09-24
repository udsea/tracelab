# Analysis and real-run visualization

TraceLab derives semantic summaries, a run outline, coordinates, relationships and analysis signals from canonical events. These additions do not replace source ingestion, Inspect execution, classifier records or legacy segments.

## Navigation

The outline combines existing segments with deterministic activity episodes, recurring activities and recorded relationship moments. Optional **Interpret outline with LLM** sends semantic event summaries, tool outcomes, agent identities, parents, timing and errors to the explicitly selected provider. Output must cite supplied event IDs. Interpretations can overlap; they need not partition the run. Legacy phase editing remains available. Deterministic overview results and model interpretations are cached locally.

**Events**, **Elapsed time** and **Model calls** share event selection and range navigation. Untimed events occupy a labeled ordinal gutter, never invented timestamps. When generation boundaries are unavailable, the model-call scale explicitly uses an assistant-message proxy. **Previous range** restores navigation after opening detail. **Expand**, **Signals only**, **All lanes** and individual lane toggles control density. Full-run activity uses aggregated bins; close views expose individual events. The event list and outline are virtualized. Agent activity is binned at low zoom; relationship pages contain at most 200 selectable edges.

Recorded parents, explicit sender/recipient envelopes and shared artifact references provide distinct relationship types. A parent does not prove communication. Shared artifacts do not establish transfer direction. An envelope may describe both endpoints in one recorded event; TraceLab does not invent a separate receiving event. Unknown agent identity stays unknown.

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
