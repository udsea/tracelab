import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  Check,
  Command,
  FolderOpen,
  GitBranch,
  Globe2,
  Layers3,
  Play,
  Plus,
  Search,
  Settings2,
  Square,
  Sun,
  Trash2,
  X,
} from 'lucide-react'
import { Dialog } from '@/components/ui/dialog'
import { AddSource } from '@/features/sources/AddSource'
import { RemoteCacheSettings } from '@/features/sources/SourcePanel'
import { Button } from '@/components/ui/button'
import {
  ErrorState,
  Field,
  Loading,
  Status,
} from '@/components/common/Primitives'
import {
  useAction,
  useJobs,
  useProviders,
  useTimeline,
  useTrajectory,
} from '@/hooks/queries'
import { rpc } from '@/lib/api'
import { json } from '@/lib/utils'
import { notify, useUI } from '@/stores/ui'
import type { Job, Provider, SearchHit, Segment } from '@/types/domain'
export function WorkspaceDialogs() {
  const ui = useUI()
  const titles: Record<string, [string, string]> = {
    import: [
      'Add trajectory source',
      'Connect a local file, Hugging Face repository, or remote trace.',
    ],
    search: [
      'Search your workspace',
      'Find text in messages, reasoning, tools, errors, and annotations.',
    ],
    commands: ['Command palette', 'Navigate TraceLab from your keyboard.'],
    settings: [
      'Provider settings',
      'One place for model endpoints and environment-based credentials.',
    ],
    jobs: ['Execution activity', 'Progress, errors, and logs for local jobs.'],
    annotate: [
      `Annotate event #${ui.selectedIndex}`,
      'Keep your observations linked to a precise event range.',
    ],
    segment: [
      'Trajectory phases',
      'Organize a long trajectory into phases and one level of episodes.',
    ],
  }
  const title = ui.modal && titles[ui.modal]
  return (
    <Dialog
      open={!!title}
      onClose={() => ui.set({ modal: null })}
      title={title?.[0] || ''}
      description={title?.[1]}
      wide={['import', 'settings', 'jobs', 'segment'].includes(ui.modal || '')}
    >
      {ui.modal === 'import' && <AddSource />}
      {ui.modal === 'search' && <SearchPanel />}
      {ui.modal === 'commands' && <Commands />}
      {ui.modal === 'settings' && <Settings />}
      {ui.modal === 'jobs' && <JobsPanel />}
      {ui.modal === 'annotate' && <AnnotationForm />}
      {ui.modal === 'segment' && <SegmentPanel />}
    </Dialog>
  )
}
function SearchPanel() {
  const ui = useUI()
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  useEffect(() => {
    const id = setTimeout(() => setDebounced(query), 220)
    return () => clearTimeout(id)
  }, [query])
  const results = useQuery({
    queryKey: ['search', ui.workspaceId, debounced],
    queryFn: () =>
      rpc<{ items: SearchHit[]; total: number; unindexedTrajectories: number }>(
        'search',
        { workspaceId: ui.workspaceId, query: debounced },
      ),
    enabled: !!debounced && !!ui.workspaceId,
  })
  const index = useAction<Job>('search.index', ['jobs'])
  return (
    <div className="dialog-body search-dialog">
      <div className="search-input">
        <Search size={17} />
        <input
          autoFocus
          placeholder="Search event content, tool names, annotations…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <kbd>↵</kbd>
      </div>
      {!ui.workspaceId && (
        <p className="muted">Open a workspace before searching.</p>
      )}
      {results.isFetching && <Loading text="Searching indexed events…" />}
      {results.error && <ErrorState error={results.error} />}{' '}
      {results.data && (
        <>
          <div className="search-summary">
            {results.data.total} matches
            {results.data.unindexedTrajectories > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  index.mutate(
                    { workspaceId: ui.workspaceId },
                    { onSuccess: () => ui.set({ modal: 'jobs' }) },
                  )
                }
              >
                Index {results.data.unindexedTrajectories} unopened trajectories
              </Button>
            )}
          </div>
          <div className="search-results">
            {results.data.items.map((hit) => (
              <button
                key={hit.id}
                onClick={() => {
                  ui.selectTrajectory(hit.trajectoryId)
                  ui.jump(hit.index)
                  ui.set({ modal: null })
                }}
              >
                <div>
                  <span>Event #{hit.index}</span>
                  <span>{hit.type}</span>
                  <ArrowRight size={12} />
                </div>
                <p>{hit.preview}</p>
              </button>
            ))}
          </div>
        </>
      )}
      {!query && (
        <p className="muted small">
          Plain text search. Unopened trajectories can be indexed in the
          background; source logs remain unchanged.
        </p>
      )}
    </div>
  )
}
function Commands() {
  const ui = useUI()
  const [q, setQ] = useState('')
  const actions = [
    {
      label: 'Add trajectory source',
      key: '⌘ O',
      icon: FolderOpen,
      run: () => ui.set({ modal: 'import' }),
    },
    {
      label: 'Search workspace',
      key: '/',
      icon: Search,
      run: () => ui.set({ modal: 'search' }),
    },
    {
      label: 'Browse trajectories',
      key: '',
      icon: Layers3,
      run: () => ui.set({ modal: null, section: 'browser' }),
    },
    {
      label: 'Create a classifier',
      key: '',
      icon: Plus,
      run: () => ui.set({ modal: null, section: 'classifiers' }),
    },
    {
      label: 'Fork selected event',
      key: 'F',
      icon: GitBranch,
      run: () => ui.set({ modal: 'fork' }),
    },
    {
      label: 'Provider settings',
      key: '',
      icon: Settings2,
      run: () => ui.set({ modal: 'settings' }),
    },
    {
      label: 'Toggle light / dark theme',
      key: '',
      icon: Sun,
      run: () =>
        ui.set({ theme: ui.theme === 'dark' ? 'light' : 'dark', modal: null }),
    },
    {
      label: 'Recent workspaces',
      key: '',
      icon: Command,
      run: () => {
        ui.setWorkspace(null)
        ui.set({ modal: null })
      },
    },
  ].filter((a) => a.label.toLowerCase().includes(q.toLowerCase()))
  return (
    <div className="dialog-body command-dialog">
      <div className="search-input">
        <Command size={16} />
        <input
          autoFocus
          placeholder="What would you like to do?"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') actions[0]?.run()
          }}
        />
      </div>
      {actions.map((a) => (
        <button className="command-row" key={a.label} onClick={a.run}>
          <a.icon size={16} />
          {a.label}
          <kbd>{a.key}</kbd>
          <ArrowRight size={13} />
        </button>
      ))}
    </div>
  )
}
function Settings() {
  const providers = useProviders()
  const [selected, setSelected] = useState('openai')
  const item = providers.data?.find((p) => p.id === selected)
  return (
    <div className="settings-layout">
      <div className="provider-tabs">
        {providers.data?.map((p) => (
          <button
            className={selected === p.id ? 'active' : ''}
            key={p.id}
            onClick={() => setSelected(p.id)}
          >
            <Globe2 size={14} />
            {p.name}
            <span
              className={`provider-dot ${p.configured ? 'configured' : ''}`}
            />
          </button>
        ))}
      </div>
      {item && (
        <div>
          <ProviderForm key={item.id} provider={item} />
          <RemoteCacheSettings />
        </div>
      )}
    </div>
  )
}
function ProviderForm({ provider }: { provider: Provider }) {
  const [form, setForm] = useState(provider)
  const save = useAction('providers.save', ['providers'])
  return (
    <div className="provider-form">
      <h3>{provider.name}</h3>
      <Field label="Display name">
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
      </Field>
      <Field label="Endpoint base URL">
        <input
          value={form.baseUrl}
          onChange={(e) => setForm({ ...form, baseUrl: e.target.value })}
        />
      </Field>
      <Field
        label="API key environment variable"
        hint="Enter the variable name, never the secret. Restart TraceLab after changing its environment."
      >
        <input
          value={form.apiKeyEnv}
          onChange={(e) => setForm({ ...form, apiKeyEnv: e.target.value })}
        />
      </Field>
      <Field label="Default model ID">
        <input
          value={form.defaultModel}
          placeholder="Your preferred model"
          onChange={(e) => setForm({ ...form, defaultModel: e.target.value })}
        />
      </Field>
      <div className="credential-status">
        <span
          className={`provider-dot ${provider.configured ? 'configured' : ''}`}
        />
        {provider.configured
          ? 'Credentials available, or local endpoint'
          : 'Environment variable is not set'}
      </div>
      <p className="muted small">
        Provider settings stay in local storage. API keys are read by Python and
        never sent to the frontend.
      </p>
      <Button
        disabled={save.isPending}
        onClick={() => {
          const { configured: _configured, ...config } = form
          save.mutate(config, {
            onSuccess: () => notify('Provider settings saved'),
          })
        }}
      >
        Save provider
      </Button>
    </div>
  )
}
function JobsPanel() {
  const ui = useUI()
  const jobs = useJobs()
  const cancel = useAction('jobs.cancel', ['jobs'])
  return (
    <div className="dialog-body jobs-panel">
      {jobs.data?.length === 0 && (
        <p className="muted">
          No jobs yet. Imports, classifiers, segmentation and forks appear here.
        </p>
      )}
      {jobs.data?.map((job) => (
        <div className="job-card" key={job.id}>
          <div className="job-heading">
            <div>
              <strong>{job.name}</strong>
              <small>
                {job.kind} · {new Date(job.createdAt).toLocaleTimeString()}
              </small>
            </div>
            <Status status={job.status} />
            {['running', 'queued'].includes(job.status) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => cancel.mutate({ id: job.id })}
              >
                <Square size={11} />
                Cancel
              </Button>
            )}
          </div>
          <div className="job-progress">
            <i
              style={{
                width: `${job.total ? (job.completed / job.total) * 100 : 0}%`,
              }}
            />
          </div>
          <div className="job-count">
            <span>
              {job.completed} / {job.total || '…'}{' '}
              {job.kind === 'classifier' ? 'inputs' : 'items'}
            </span>
            <span>{job.concurrency} concurrently</span>
          </div>
          {job.error && <div className="inline-error">{job.error}</div>}
          <details className="raw-details">
            <summary>Execution logs</summary>
            <pre>{job.logs.join('\n')}</pre>
          </details>
          {job.kind === 'fork' && job.status === 'complete' && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => ui.set({ section: 'forks', modal: null })}
            >
              View branches & compare
              <ArrowRight size={12} />
            </Button>
          )}
        </div>
      ))}
    </div>
  )
}
function AnnotationForm() {
  const ui = useUI()
  const [label, setLabel] = useState('REVIEW')
  const [note, setNote] = useState('')
  const [start, setStart] = useState(ui.selectedIndex)
  const [end, setEnd] = useState(ui.selectedIndex)
  const timeline = useTimeline(ui.trajectoryId)
  const save = useAction('annotations.save', ['timeline', 'event'])
  const remove = useAction('annotations.delete', ['timeline', 'event'])
  return (
    <div className="dialog-body">
      <Field label="Label">
        <input
          list="annotation-labels"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <datalist id="annotation-labels">
          {[
            'EVAL_AWARE',
            'STRATEGY_CHANGE',
            'HARNESS_BUG',
            'SUSPICIOUS',
            'INTERESTING',
            'REVIEW',
          ].map((l) => (
            <option key={l}>{l}</option>
          ))}
        </datalist>
      </Field>
      <div className="form-row">
        <Field label="Start event">
          <input
            type="number"
            min={0}
            value={start}
            onChange={(e) => setStart(+e.target.value)}
          />
        </Field>
        <Field label="End event">
          <input
            type="number"
            min={start}
            value={end}
            onChange={(e) => setEnd(+e.target.value)}
          />
        </Field>
      </div>
      <Field label="Observation">
        <textarea
          rows={4}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What did you notice?"
        />
      </Field>
      <div className="form-actions">
        <Button
          disabled={!ui.trajectoryId || !label || save.isPending}
          onClick={() =>
            save.mutate(
              {
                trajectoryId: ui.trajectoryId,
                startEventIndex: start,
                endEventIndex: end,
                label,
                note,
              },
              {
                onSuccess: () => {
                  ui.set({ modal: null })
                  notify('Annotation saved')
                },
              },
            )
          }
        >
          Save annotation
        </Button>
      </div>
      {timeline.data?.annotations
        .filter(
          (a) =>
            a.startEventIndex <= ui.selectedIndex &&
            a.endEventIndex >= ui.selectedIndex,
        )
        .map((a) => (
          <div className="text-row" key={a.id}>
            <span>
              {a.label} · #{a.startEventIndex}–{a.endEventIndex}
            </span>
            <Button
              variant="ghost"
              size="icon"
              title="Delete annotation"
              onClick={() => remove.mutate({ id: a.id })}
            >
              <Trash2 size={13} />
            </Button>
          </div>
        ))}
    </div>
  )
}
function SegmentPanel() {
  const ui = useUI()
  const trajectory = useTrajectory(ui.trajectoryId)
  const timeline = useTimeline(ui.trajectoryId)
  const providers = useProviders()
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState('')
  const run = useAction<Job>('segments.run', ['jobs'])
  return (
    <div className="dialog-body">
      <div className="segment-edit-list">
        {timeline.data?.segments.map((s) => (
          <SegmentEditor key={s.id} segment={s} />
        ))}
      </div>
      <div className="segment-generate">
        <h3>
          {timeline.data?.segments.length
            ? 'Regenerate segmentation'
            : 'Find the phases in this trajectory'}
        </h3>
        <p className="muted">
          Uses event previews (up to 1,200 characters each). Full source events
          remain intact. A validated result replaces the current phases.
        </p>
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
          <Field label="Model">
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Model ID"
            />
          </Field>
        </div>
        <div className="form-actions">
          <span>
            {trajectory.data?.trajectory.eventCount || 0} events · cached by
            exact input
          </span>
          <Button
            disabled={!model || !ui.trajectoryId || run.isPending}
            onClick={() =>
              run.mutate(
                { trajectoryId: ui.trajectoryId, provider, model },
                { onSuccess: () => ui.set({ modal: 'jobs' }) },
              )
            }
          >
            <Play size={13} />
            Generate phases
          </Button>
        </div>
      </div>
    </div>
  )
}
function SegmentEditor({ segment }: { segment: Segment }) {
  const [item, setItem] = useState(segment)
  const save = useAction('segments.save', ['timeline'])
  const remove = useAction('segments.delete', ['timeline'])
  return (
    <div
      className={`segment-editor ${segment.parentId ? 'segment-episode' : ''}`}
    >
      <input
        aria-label="Segment label"
        value={item.label}
        onChange={(e) => setItem({ ...item, label: e.target.value })}
      />
      <input
        aria-label="Start event"
        type="number"
        value={item.startEvent}
        onChange={(e) => setItem({ ...item, startEvent: +e.target.value })}
      />
      <span>–</span>
      <input
        aria-label="End event"
        type="number"
        value={item.endEvent}
        onChange={(e) => setItem({ ...item, endEvent: +e.target.value })}
      />
      <Button
        variant="ghost"
        size="icon"
        title="Save segment"
        onClick={() =>
          save.mutate(item, { onSuccess: () => notify('Segment saved') })
        }
      >
        <Check size={13} />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        title="Delete segment"
        onClick={() => remove.mutate({ id: item.id })}
      >
        <X size={13} />
      </Button>
      <details className="segment-provenance">
        <summary>Provenance</summary>
        <pre>{json(segment.provenance)}</pre>
      </details>
    </div>
  )
}
