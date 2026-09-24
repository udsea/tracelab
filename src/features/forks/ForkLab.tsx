import {
  defaultExecution,
  ExecutionOptions,
  ExecutionSummary,
  parseStubs,
  ReplaySummary,
  type ReplayPreview,
} from './ExecutionOptions'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  Check,
  GitBranch,
  Info,
  Play,
  Plus,
  Trash2,
  X,
} from 'lucide-react'
import { Dialog } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Empty, Field, Loading, Status } from '@/components/common/Primitives'
import {
  useAction,
  useProviders,
  useTrajectory,
  useTrajectories,
} from '@/hooks/queries'
import { notify, useUI } from '@/stores/ui'
import { rpc } from '@/lib/api'
import { eventLabel } from '@/lib/utils'
import type { Fork, Intervention, Job, TrajectoryEvent } from '@/types/domain'
import {
  buildGenerationParameters,
  defaultGeneration,
  defaultIntervention,
  estimateTokens,
  lineDiff,
  originalFor,
  replacementBlocked,
  targets,
  toInterventions,
  type EditorIntervention,
} from './request'
const interventionLabels: Record<Intervention['type'], string> = {
  remove_event: 'Remove event',
  replace_content: 'Replace content',
  replace_tool_result: 'Replace tool result',
  append_message: 'Append message',
  system_prompt_override: 'Override system prompt',
  model_override: 'Change model',
  generation_override: 'Change generation parameters',
}
export function ForkDialog() {
  const ui = useUI()
  return (
    <Dialog
      open={ui.modal === 'fork'}
      onClose={() => ui.set({ modal: null })}
      title={`Fork from event #${ui.selectedIndex}`}
      description="Create a reproducible intervention branch. The source remains intact."
      wide
    >
      {ui.modal === 'fork' && ui.trajectoryId && (
        <ForkForm
          key={`${ui.trajectoryId}:${ui.selectedIndex}`}
          trajectoryId={ui.trajectoryId}
          selectedIndex={ui.selectedIndex}
        />
      )}
    </Dialog>
  )
}

const useEventAt = (trajectoryId: string, index: number, enabled = true) =>
  useQuery({
    // Same key as the inspector, so the selected event is usually already cached.
    queryKey: ['event', trajectoryId, index],
    queryFn: () =>
      rpc<{ event: TrajectoryEvent; results: unknown[] }>('events.get', {
        trajectoryId,
        index,
      }),
    enabled,
  })

interface Preview extends ReplayPreview {
  sourceEventIndex: number
  model: string
  provider: {
    id: string
    name: string
    kind: string
    baseUrl: string
    apiKeyEnv: string
  }
  parameters: Record<string, unknown>
  seedIncrementsByReplication: boolean
  replicationCount: number
  messages: unknown[]
  inputHash: string
  contextCharacters: number
}

export function ForkForm({
  trajectoryId,
  selectedIndex,
}: {
  trajectoryId: string
  selectedIndex: number
}) {
  const ui = useUI()
  const source = useTrajectory(trajectoryId)
  const providers = useProviders()
  const selected = useEventAt(trajectoryId, selectedIndex)
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState(
    source.data?.trajectory.model?.startsWith('example/')
      ? ''
      : source.data?.trajectory.model || '',
  )
  const [replications, setReplications] = useState(1)
  const [execution, setExecution] = useState(defaultExecution)
  const [stubText, setStubText] = useState('[]')
  const stubs = parseStubs(stubText)
  const multi = execution.continuation === 'multi_step'
  const [generation, setGeneration] = useState(defaultGeneration)
  const [items, setItems] = useState<EditorIntervention[] | null>(null)
  const [nextKey, setNextKey] = useState(1)
  const [fidelityOpen, setFidelityOpen] = useState(false)
  const event = selected.data?.event
  useEffect(() => {
    // The first intervention targets the selected event, not a typed index.
    if (items === null && (event || selected.error))
      setItems([defaultIntervention(event, selectedIndex)])
  }, [event, selected.error, items, selectedIndex])
  const action = useAction<Job>('forks.run', ['jobs', 'forks', 'trajectories'])
  const params = buildGenerationParameters(generation)
  const built = toInterventions(trajectoryId, items ?? [])
  const localError =
    params.error ??
    built.error ??
    (multi && execution.unmatchedToolPolicy === 'stub'
      ? stubs.error
      : undefined) ??
    (multi &&
    (!Number.isInteger(execution.maxModelSteps) ||
      execution.maxModelSteps < 1 ||
      execution.maxModelSteps > 100 ||
      !Number.isInteger(execution.maxToolCalls) ||
      execution.maxToolCalls < 1 ||
      execution.maxToolCalls > 1000)
      ? 'Enter valid model/tool call bounds.'
      : undefined)
  const replicationCount = Math.max(1, Math.min(100, replications || 1))
  const request = {
    sourceTrajectoryId: trajectoryId,
    sourceEventId: `${trajectoryId}:e${selectedIndex}`,
    fidelity: 'context_only',
    interventions: built.interventions,
    modelOverrides: { provider, model, parameters: params.parameters },
    replicationCount,
    executionSpec: {
      ...execution,
      toolStubs:
        multi && execution.unmatchedToolPolicy === 'stub' ? stubs.stubs : [],
    },
  }
  const requestKey = JSON.stringify(request)
  const [debounced, setDebounced] = useState(requestKey)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(requestKey), 350)
    return () => clearTimeout(id)
  }, [requestKey])
  const preview = useQuery({
    queryKey: ['fork-preview', debounced],
    queryFn: () => rpc<Preview>('forks.preview', JSON.parse(debounced)),
    enabled: items !== null && !localError,
    retry: false,
  })
  const contextOnly = !!source.data?.capabilities.contextOnly
  function change(index: number, patch: Partial<EditorIntervention>) {
    setItems((current) =>
      (current ?? []).map((item, i) =>
        i === index ? { ...item, ...patch } : item,
      ),
    )
  }
  async function run() {
    try {
      await action.mutateAsync(request)
      ui.set({ modal: 'jobs', section: 'forks' })
    } catch (error) {
      notify(String(error))
    }
  }
  const maxTokens = params.parameters.max_tokens as number | undefined
  return (
    <div className="dialog-body fork-form">
      {source.data && !contextOnly && (
        <div className="inline-error">
          Fork unavailable: {source.data.capabilities.reason}
        </div>
      )}
      <div className="fork-source">
        <GitBranch size={17} />
        <div>
          <strong>sample_{source.data?.trajectory.sampleId}</strong>
          <span>
            Prefix through event #{selectedIndex} · {selectedIndex + 1} recorded
            event{selectedIndex === 0 ? '' : 's'}
          </span>
        </div>
        <button
          className="tag fidelity-badge"
          aria-expanded={fidelityOpen}
          aria-controls="fork-fidelity"
          title="What a context-only fork restores"
          onClick={() => setFidelityOpen(!fidelityOpen)}
        >
          CONTEXT-ONLY <Info size={11} aria-hidden />
        </button>
      </div>
      {fidelityOpen && (
        <div className="fidelity-panel" id="fork-fidelity">
          <ul>
            <li>
              <Check size={12} aria-hidden /> Recorded conversational context is
              restored
            </li>
            <li>
              <X size={12} aria-hidden /> Original filesystem and process state
              are unavailable
            </li>
            <li>
              <X size={12} aria-hidden /> Arbitrary external state (APIs,
              services) is unavailable
            </li>
            <li>
              <X size={12} aria-hidden /> The original tool scaffold is
              unavailable; generated calls are never executed
            </li>
            <li>
              <Info size={12} aria-hidden /> Each branch is initially unscored
            </li>
          </ul>
          <p>
            {multi
              ? 'Multiple model calls may use exact recorded observations.'
              : 'One model continuation per replication runs through Inspect.'}{' '}
            {source.data?.capabilities.reason}
          </p>
        </div>
      )}
      {event?.type === 'tool_call' && (
        <div className="inline-warning">
          Event #{selectedIndex} is a tool call, so its result would be missing
          from the context. Fork after its result instead.
          <Button
            size="sm"
            variant="outline"
            onClick={() => ui.select(selectedIndex + 1)}
          >
            Use #{selectedIndex + 1}
          </Button>
        </div>
      )}
      <div className="detail-heading intervention-heading">
        INTERVENTIONS
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setItems((current) => [
              ...(current ?? []),
              {
                key: nextKey,
                type: 'append_message',
                targetIndex: selectedIndex,
                text: '',
                original: null,
                role: 'user',
              },
            ])
            setNextKey(nextKey + 1)
          }}
        >
          <Plus size={13} />
          Add intervention
        </Button>
      </div>
      {items === null ? (
        <Loading text={`Loading event #${selectedIndex}…`} />
      ) : (
        items.map((item, index) => (
          <InterventionEditor
            key={item.key}
            number={index + 1}
            item={item}
            trajectoryId={trajectoryId}
            maxIndex={selectedIndex}
            onChange={(patch) => change(index, patch)}
            onRemove={() =>
              setItems((current) =>
                (current ?? []).filter((_, i) => i !== index),
              )
            }
          />
        ))
      )}
      <div className="detail-heading">CONTINUATION</div>
      <ExecutionOptions
        value={execution}
        onChange={setExecution}
        stubs={stubText}
        onStubs={setStubText}
      />
      {multi && (
        <ReplaySummary
          preview={debounced === requestKey ? preview.data : undefined}
        />
      )}
      <div className="form-row">
        <Field label="Provider">
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value)
              const fallback = providers.data?.find(
                (p) => p.id === e.target.value,
              )?.defaultModel
              if (fallback) setModel(fallback)
            }}
          >
            {providers.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Continuation model">
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="Model ID"
          />
        </Field>
        <Field label="Replications">
          <input
            type="number"
            min={1}
            max={100}
            value={replications}
            onChange={(e) => setReplications(+e.target.value)}
          />
        </Field>
      </div>
      <div className="form-row">
        <Field label="Temperature" hint="Blank uses the provider default">
          <input
            inputMode="decimal"
            value={generation.temperature}
            placeholder="default"
            onChange={(e) =>
              setGeneration({ ...generation, temperature: e.target.value })
            }
          />
        </Field>
        <Field label="Max output tokens">
          <input
            inputMode="numeric"
            value={generation.maxTokens}
            onChange={(e) =>
              setGeneration({ ...generation, maxTokens: e.target.value })
            }
          />
        </Field>
        <Field
          label="Seed"
          hint="Increments by replication; provider support varies"
        >
          <input
            inputMode="numeric"
            value={generation.seed}
            placeholder="none"
            onChange={(e) =>
              setGeneration({ ...generation, seed: e.target.value })
            }
          />
        </Field>
      </div>
      <details className="raw-details">
        <summary>Advanced generation parameters (JSON)</summary>
        <Field
          label="Additional parameters"
          hint="Supported: top_p, top_k, reasoning_effort, reasoning_tokens, stop_seqs"
        >
          <textarea
            className="mono"
            rows={3}
            value={generation.advanced}
            placeholder='{"top_p": 0.9}'
            onChange={(e) =>
              setGeneration({ ...generation, advanced: e.target.value })
            }
          />
        </Field>
      </details>
      {localError && <div className="inline-error">{localError}</div>}
      {preview.error && !localError && (
        <div className="inline-error">{preview.error.message}</div>
      )}
      <details className="raw-details fork-preview">
        <summary>Preview continuation input</summary>
        {preview.data ? (
          <div className="fork-preview-body">
            <dl>
              <dt>Provider</dt>
              <dd>
                {preview.data.provider.name} · {preview.data.provider.baseUrl} ·
                key read from ${preview.data.provider.apiKeyEnv}
              </dd>
              <dt>Model</dt>
              <dd>
                {preview.data.model}
                {!model &&
                  ' (recorded model; enter a continuation model to run)'}
              </dd>
              <dt>Generation</dt>
              <dd className="mono">
                {JSON.stringify(preview.data.parameters)}
              </dd>
              <dt>Replications</dt>
              <dd>
                {preview.data.replicationCount}
                {preview.data.seedIncrementsByReplication &&
                  ' · seed increments by replication'}
              </dd>
              <dt>Input hash</dt>
              <dd className="mono">{preview.data.inputHash.slice(0, 16)}…</dd>
            </dl>
            <pre>{JSON.stringify(preview.data.messages, null, 2)}</pre>
          </div>
        ) : (
          <p className="muted">
            {localError
              ? 'Fix the highlighted input to preview the request.'
              : 'Reconstructing the edited context…'}
          </p>
        )}
      </details>
      <div className="form-actions">
        <span className="fork-estimate">
          {preview.data
            ? `≈${estimateTokens(preview.data.contextCharacters).toLocaleString()} context tokens (character estimate)`
            : 'Context size pending'}
          {maxTokens
            ? ` · up to ${maxTokens.toLocaleString()} output tokens`
            : ''}{' '}
          {multi && `per model call × up to ${execution.maxModelSteps} steps `}×{' '}
          {replicationCount} replication{replicationCount === 1 ? '' : 's'} ·
          Monetary cost unavailable
          <small>Context is sent to the selected provider.</small>
        </span>
        <Button
          disabled={
            !model ||
            action.isPending ||
            !contextOnly ||
            !!localError ||
            !!preview.error ||
            (multi &&
              (debounced !== requestKey ||
                preview.isFetching ||
                !preview.data?.replaySupport.supported))
          }
          onClick={() => {
            void run()
          }}
        >
          <Play size={13} />
          Run{' '}
          {replicationCount > 1 ? `${replicationCount} replications` : 'fork'}
        </Button>
      </div>
    </div>
  )
}

function InterventionEditor({
  number,
  item,
  trajectoryId,
  maxIndex,
  onChange,
  onRemove,
}: {
  number: number
  item: EditorIntervention
  trajectoryId: string
  maxIndex: number
  onChange: (patch: Partial<EditorIntervention>) => void
  onRemove: () => void
}) {
  const [changingTarget, setChangingTarget] = useState(false)
  const hasTarget = targets(item.type)
  const target = useEventAt(trajectoryId, item.targetIndex, hasTarget)
  const event = target.data?.event
  const replaces =
    item.type === 'replace_content' || item.type === 'replace_tool_result'
  const blocked = replaces ? replacementBlocked(event) : null
  useEffect(() => {
    // Replacements start from the target's original content.
    if (replaces && event && item.original === null) {
      const original = originalFor(item.type, event) ?? ''
      onChange({ original, text: item.text || original })
    }
  }, [replaces, event, item.original, item.type])
  const diff =
    replaces && item.original !== null && item.text !== item.original
      ? lineDiff(item.original, item.text)
      : null
  return (
    <div className="intervention-editor">
      <div className="intervention-top">
        <span>{String(number).padStart(2, '0')}</span>
        <select
          aria-label={`Intervention ${number} type`}
          value={item.type}
          onChange={(e) =>
            onChange({
              type: e.target.value as Intervention['type'],
              original: null,
              text: '',
            })
          }
        >
          {Object.entries(interventionLabels).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        {hasTarget && (
          <span className="intervention-target">
            Event #{item.targetIndex}
            {event && ` · ${event.tool?.name || eventLabel(event.type)}`}
            <button
              className="text-button"
              aria-expanded={changingTarget}
              onClick={() => setChangingTarget(!changingTarget)}
            >
              Change target
            </button>
          </span>
        )}
        <Button
          variant="ghost"
          size="icon"
          title="Remove intervention"
          aria-label={`Remove intervention ${number}`}
          onClick={onRemove}
        >
          <Trash2 size={13} />
        </Button>
      </div>
      {hasTarget && changingTarget && (
        <Field
          label="Target event index"
          hint={`Any event from #0 to #${maxIndex} in the prefix`}
        >
          <input
            type="number"
            min={0}
            max={maxIndex}
            value={item.targetIndex}
            onChange={(e) =>
              onChange({
                targetIndex: Math.max(0, Math.min(maxIndex, +e.target.value)),
                original: null,
                text: '',
              })
            }
          />
        </Field>
      )}
      {blocked && <div className="inline-warning">{blocked}</div>}
      {item.type === 'append_message' && (
        <Field label="Role">
          <select
            value={item.role}
            onChange={(e) => onChange({ role: e.target.value })}
          >
            <option>user</option>
            <option>assistant</option>
            <option>system</option>
          </select>
        </Field>
      )}
      {replaces ? (
        <div className="replacement-grid">
          <div>
            <span className="replacement-label">Original</span>
            <pre
              className="replacement-original"
              data-testid="original-content"
            >
              {item.original ?? (target.isLoading ? 'Loading…' : '—')}
            </pre>
          </div>
          <label>
            <span className="replacement-label">
              Replacement
              {item.type === 'replace_tool_result' && ' (JSON)'}
            </span>
            <textarea
              rows={6}
              value={item.text}
              onChange={(e) => onChange({ text: e.target.value })}
            />
          </label>
        </div>
      ) : (
        item.type !== 'remove_event' && (
          <textarea
            rows={3}
            aria-label={`Intervention ${number} value`}
            placeholder={
              item.type === 'generation_override'
                ? 'Valid JSON object'
                : item.type === 'model_override'
                  ? 'Model ID'
                  : 'New content…'
            }
            value={item.text}
            onChange={(e) => onChange({ text: e.target.value })}
          />
        )
      )}
      {replaces && item.original !== null && item.text !== item.original && (
        <details className="raw-details" open>
          <summary>
            Changes
            {diff
              ? ` · +${diff.filter((d) => d.op === '+').length} −${diff.filter((d) => d.op === '-').length} lines`
              : ' · too large for a line diff'}
          </summary>
          {diff && (
            <pre className="line-diff">
              {diff.map((d, i) => (
                <span
                  key={i}
                  className={
                    d.op === '+'
                      ? 'diff-add'
                      : d.op === '-'
                        ? 'diff-del'
                        : 'diff-same'
                  }
                >
                  {d.op} {d.text}
                </span>
              ))}
            </pre>
          )}
        </details>
      )}
    </div>
  )
}
export function ForkWorkspace() {
  const ui = useUI()
  const trajectory = useTrajectory(ui.trajectoryId)
  const trajectories = useTrajectories(ui.workspaceId)
  const forks = useQuery({
    queryKey: ['forks', ui.workspaceId],
    queryFn: () => rpc<Fork[]>('forks.list', { workspaceId: ui.workspaceId }),
    enabled: !!ui.workspaceId,
    refetchInterval: 2500,
  })
  return (
    <div className="feature-page">
      <div className="feature-heading">
        <div>
          <span className="eyebrow">INTERVENTION WORKBENCH</span>
          <h1>Fork lab</h1>
          <p>Change one part of the history. Observe what follows.</p>
        </div>
        <Button
          disabled={
            !ui.trajectoryId || !trajectory.data?.capabilities.contextOnly
          }
          title={`Fork from the selected event (#${ui.selectedIndex}) of the open trajectory`}
          onClick={() => ui.set({ modal: 'fork' })}
        >
          <GitBranch size={14} />
          Fork selected event
        </Button>
      </div>
      <div className="fork-workspace-note">
        <Info size={15} />
        <span>
          Intervention points and behavioural divergence are tracked separately.
          Comparisons are descriptive, not automatic causal claims.
        </span>
      </div>
      {!forks.data?.length ? (
        <Empty
          icon={<GitBranch size={30} />}
          title="Every branch starts with a question."
          action={
            <Button
              variant="outline"
              disabled={
                !ui.trajectoryId || !trajectory.data?.capabilities.contextOnly
              }
              onClick={() => ui.set({ modal: 'fork' })}
            >
              <Plus size={14} />
              Create your first fork
            </Button>
          }
        >
          Select a trajectory event, apply an intervention, and execute a
          context-only continuation. Each replication becomes a normal
          trajectory.
        </Empty>
      ) : (
        <div className="fork-tree">
          {forks.data.map((f) => (
            <div className="fork-tree-group" key={f.id}>
              <div className="fork-tree-parent">
                <span className="fork-node">
                  <GitBranch size={17} />
                </span>
                <div>
                  <strong>
                    sample_
                    {trajectories.data?.items.find(
                      (t) => t.id === f.sourceTrajectoryId,
                    )?.sampleId || 'Original trajectory'}
                  </strong>
                  <span>Fork at #{f.sourceEventId.split(':e').at(-1)}</span>
                </div>
                {!!f.metadata.synthetic && (
                  <span
                    className="tag"
                    title={String(f.metadata.note ?? 'Synthetic sample data')}
                  >
                    SYNTHETIC
                  </span>
                )}
                <span className="tag">CONTEXT ONLY</span>
                <Status status={f.status} />
              </div>
              <div className="fork-intervention-label">
                {f.interventions
                  .map((i) => interventionLabels[i.type])
                  .join(' + ') || 'Unmodified continuation'}
              </div>
              {f.metadata.error != null && (
                <div className="inline-error">{String(f.metadata.error)}</div>
              )}
              {f.childTrajectoryIds.map((id, i) => (
                <div className="fork-tree-child" key={id}>
                  <span className="branch-line" />
                  <button onClick={() => ui.selectTrajectory(id)}>
                    <span className="branch-node" />
                    <strong>Replication {i + 1}</strong>
                    <ExecutionSummary
                      metadata={
                        trajectories.data?.items.find((t) => t.id === id)
                          ?.metadata
                      }
                    />
                    <Status
                      status={
                        trajectories.data?.items.find((t) => t.id === id)
                          ?.status || 'unknown'
                      }
                    />
                    <ArrowRight size={14} />
                  </button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      ui.set({
                        trajectoryId: f.sourceTrajectoryId,
                        comparisonRight: id,
                        section: 'compare',
                      })
                    }
                  >
                    Compare to parent
                    <ArrowRight size={12} />
                  </Button>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
