import { useState } from 'react'
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
import { Empty, Field, Status } from '@/components/common/Primitives'
import {
  useAction,
  useProviders,
  useTrajectory,
  useTrajectories,
} from '@/hooks/queries'
import { notify, useUI } from '@/stores/ui'
import { rpc } from '@/lib/api'
import type { Fork, Intervention, Job } from '@/types/domain'
const interventionLabels: Record<Intervention['type'], string> = {
  remove_event: 'Remove event',
  replace_content: 'Replace content',
  replace_tool_result: 'Replace tool result',
  append_message: 'Append message',
  system_prompt_override: 'Override system prompt',
  model_override: 'Change model',
  generation_override: 'Change generation parameters',
}
type EditorIntervention = {
  type: Intervention['type']
  eventId: string
  text: string
  role: string
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
      {ui.modal === 'fork' && <ForkForm />}
    </Dialog>
  )
}
function ForkForm() {
  const ui = useUI()
  const source = useTrajectory(ui.trajectoryId)
  const providers = useProviders()
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState(
    source.data?.trajectory.model?.startsWith('example/')
      ? ''
      : source.data?.trajectory.model || '',
  )
  const [replications, setReplications] = useState(1)
  const [interventions, setInterventions] = useState<EditorIntervention[]>([
    {
      type: 'replace_content',
      eventId: `${ui.trajectoryId}:e${ui.selectedIndex}`,
      text: '',
      role: 'user',
    },
  ])
  const [parameters, setParameters] = useState('{"max_tokens": 2048}')
  const action = useAction<Job>('forks.run', ['jobs', 'forks', 'trajectories'])
  function change(index: number, patch: Partial<EditorIntervention>) {
    setInterventions((items) =>
      items.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    )
  }
  async function run() {
    try {
      const items: Intervention[] = interventions.map((item) => {
        if (item.type === 'remove_event')
          return { type: item.type, eventId: item.eventId }
        if (item.type === 'replace_content')
          return { type: item.type, eventId: item.eventId, content: item.text }
        if (item.type === 'replace_tool_result')
          return {
            type: item.type,
            eventId: item.eventId,
            value: JSON.parse(item.text),
          }
        if (item.type === 'append_message')
          return { type: item.type, role: item.role, content: item.text }
        if (item.type === 'system_prompt_override')
          return { type: item.type, content: item.text }
        if (item.type === 'model_override')
          return { type: item.type, model: item.text }
        return { type: item.type, parameters: JSON.parse(item.text) }
      })
      await action.mutateAsync({
        sourceTrajectoryId: ui.trajectoryId,
        sourceEventId: `${ui.trajectoryId}:e${ui.selectedIndex}`,
        fidelity: 'context_only',
        interventions: items,
        modelOverrides: { provider, model, parameters: JSON.parse(parameters) },
        replicationCount: replications,
      })
      ui.set({ modal: 'jobs', section: 'forks' })
    } catch (error) {
      notify(String(error))
    }
  }
  return (
    <div className="dialog-body">
      {source.data && !source.data.capabilities.contextOnly && (
        <div className="inline-error">
          Fork unavailable: {source.data.capabilities.reason}
        </div>
      )}
      <div className="fork-source">
        <GitBranch size={17} />
        <div>
          <strong>sample_{source.data?.trajectory.sampleId}</strong>
          <span>
            Prefix through event #{ui.selectedIndex} · {ui.selectedIndex + 1}{' '}
            source events
          </span>
        </div>
        <span className="tag">CONTEXT ONLY</span>
      </div>
      <div className="fidelity-panel">
        <div>
          <h4>CONTEXT-ONLY FORK</h4>
          <span>
            <Check size={12} />
            Recorded conversation context
          </span>
        </div>
        <div>
          <span>
            <X size={12} />
            Filesystem & running processes
          </span>
          <span>
            <X size={12} />
            External APIs & arbitrary environment state
          </span>
        </div>
        <p>
          Executes one real model continuation through Inspect. Original tools,
          agent scaffold, and scorer are unavailable. Branch outcome remains
          unscored.
        </p>
      </div>
      <label
        className="disabled-option"
        title={source.data?.capabilities.reason}
      >
        <input type="radio" disabled />
        Checkpoint restoration unavailable
        <Info size={13} />
      </label>
      <p className="muted small">{source.data?.capabilities.reason}</p>
      <div className="detail-heading intervention-heading">
        INTERVENTIONS
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            setInterventions((items) => [
              ...items,
              {
                type: 'append_message',
                eventId: `${ui.trajectoryId}:e${ui.selectedIndex}`,
                text: '',
                role: 'user',
              },
            ])
          }
        >
          <Plus size={13} />
          Add intervention
        </Button>
      </div>
      {interventions.map((item, index) => (
        <div className="intervention-editor" key={index}>
          <div className="intervention-top">
            <span>{String(index + 1).padStart(2, '0')}</span>
            <select
              value={item.type}
              onChange={(e) =>
                change(index, { type: e.target.value as Intervention['type'] })
              }
            >
              {Object.entries(interventionLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <Button
              variant="ghost"
              size="icon"
              title="Remove intervention"
              onClick={() =>
                setInterventions((items) => items.filter((_, i) => i !== index))
              }
            >
              <Trash2 size={13} />
            </Button>
          </div>
          {['remove_event', 'replace_content', 'replace_tool_result'].includes(
            item.type,
          ) && (
            <Field label="Event index">
              <input
                type="number"
                min={0}
                max={ui.selectedIndex}
                value={Number(item.eventId.split(':e').at(-1))}
                onChange={(e) =>
                  change(index, {
                    eventId: `${ui.trajectoryId}:e${e.target.value}`,
                  })
                }
              />
            </Field>
          )}
          {item.type === 'append_message' && (
            <Field label="Role">
              <select
                value={item.role}
                onChange={(e) => change(index, { role: e.target.value })}
              >
                <option>user</option>
                <option>assistant</option>
                <option>system</option>
              </select>
            </Field>
          )}
          {item.type !== 'remove_event' && (
            <textarea
              rows={3}
              placeholder={
                ['replace_tool_result', 'generation_override'].includes(
                  item.type,
                )
                  ? 'Valid JSON value'
                  : item.type === 'model_override'
                    ? 'Model ID'
                    : 'New content…'
              }
              value={item.text}
              onChange={(e) => change(index, { text: e.target.value })}
            />
          )}
        </div>
      ))}
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
      <Field
        label="Generation parameters (JSON)"
        hint="An explicit seed increments by replication. Provider support for seeds varies."
      >
        <input
          className="mono"
          value={parameters}
          onChange={(e) => setParameters(e.target.value)}
        />
      </Field>
      <div className="form-actions">
        <span>Context is sent to the selected provider.</span>
        <Button
          disabled={
            !model ||
            !ui.trajectoryId ||
            action.isPending ||
            !source.data?.capabilities.contextOnly
          }
          onClick={() => {
            void run()
          }}
        >
          <Play size={13} />
          Run {replications > 1 ? `${replications} replications` : 'fork'}
        </Button>
      </div>
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
                    {trajectories.data?.items.find(
                      (t) => t.id === f.sourceTrajectoryId,
                    )?.sampleId || 'Original trajectory'}
                  </strong>
                  <span>Fork at #{f.sourceEventId.split(':e').at(-1)}</span>
                </div>
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
                    <span>
                      {trajectories.data?.items.find((t) => t.id === id)
                        ?.status || 'Open trajectory'}
                    </span>
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
