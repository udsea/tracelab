import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  File,
  Folder,
  FolderOpen,
  Globe2,
  Search,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ErrorState, Field, Loading } from '@/components/common/Primitives'
import { useAction } from '@/hooks/queries'
import { chooseLogs, rpc } from '@/lib/api'
import { notify, useUI } from '@/stores/ui'
import type { Job, Workspace } from '@/types/domain'
import {
  bytes,
  type SourceEntry,
  type SourceRef,
  type SourceDetection,
} from '@/types/sources'
import { MappingReview, type MappingApproval } from './MappingReview'

interface BundleProposal {
  ref: SourceRef
  streams: SourceEntry[]
  scores: SourceEntry[]
  configs: SourceEntry[]
  artifacts: SourceEntry[]
}

export function AddSource() {
  const ui = useUI()
  const [kind, setKind] = useState<'local' | 'huggingface' | 'http'>('local')
  const [uri, setUri] = useState('')
  const [repoType, setRepoType] = useState('dataset')
  const [revision, setRevision] = useState('main')
  const [name, setName] = useState('My research')
  const [root, setRoot] = useState<SourceEntry | null>(null)
  const [trail, setTrail] = useState<SourceEntry[]>([])
  const [selected, setSelected] = useState<Record<string, SourceRef>>({})
  const [detections, setDetections] = useState<Record<string, SourceDetection>>(
    {},
  )
  const [search, setSearch] = useState('')
  const [probing, setProbing] = useState(false)
  const [mappings, setMappings] = useState<Record<string, MappingApproval>>({})
  const connect = useAction<SourceEntry>('sources.connect')
  const create = useAction<Workspace>('workspaces.create', ['workspaces'])
  const add = useAction<Job>('sources.add', [
    'jobs',
    'workspaces',
    'trajectories',
    'experiments',
  ])
  const bundle = useAction<BundleProposal>('sources.bundle')
  const addBundle = useAction<Job>('sources.addBundle', [
    'jobs',
    'workspaces',
    'trajectories',
    'experiments',
  ])
  const current = trail.at(-1) || root
  const entries = useQuery({
    queryKey: ['source-files', current?.ref, !!search],
    queryFn: () =>
      rpc<SourceEntry[]>('sources.list', {
        ref: current!.ref,
        recursive: !!search,
      }),
    enabled: !!current?.isDirectory,
  })
  const items = (
    current?.isDirectory ? entries.data || [] : current ? [current] : []
  ).filter(
    (e) =>
      !search ||
      (e.path || e.name).toLowerCase().includes(search.toLowerCase()),
  )
  async function inspect(ref: SourceRef) {
    const result = await rpc<SourceDetection>('sources.detect', { ref })
    setDetections((old) => ({ ...old, [ref.uri]: result }))
    return result
  }
  async function open() {
    const value = await connect.mutateAsync({ uri, kind, repoType, revision })
    setRoot(value)
    setTrail([])
    setSelected(value.isDirectory ? {} : { [value.ref.uri]: value.ref })
    setDetections({})
    setSearch('')
    bundle.reset()
    if (!value.isDirectory) await inspect(value.ref)
  }
  async function pick(directory: boolean) {
    const chosen = await chooseLogs(directory)
    if (chosen) {
      setUri(chosen)
      setRoot(null)
    } else notify('Enter a local path when using the browser preview.')
  }
  async function probe() {
    setProbing(true)
    try {
      for (const ref of Object.values(selected)) await inspect(ref)
    } catch (error) {
      notify(String(error))
    } finally {
      setProbing(false)
    }
  }
  async function submit() {
    let needsReview = false
    for (const ref of Object.values(selected)) {
      const d = detections[ref.uri] || (await inspect(ref))
      if (d.mapping && !d.knownProfile && !mappings[ref.uri]) needsReview = true
    }
    if (needsReview) {
      notify(
        'Review and approve the proposed generic mappings below before importing.',
      )
      return
    }
    let workspaceId = ui.workspaceId
    if (!workspaceId) {
      const workspace = await create.mutateAsync({ name })
      workspaceId = workspace.id
      ui.setWorkspace(workspaceId)
    }
    await add.mutateAsync({
      workspaceId,
      refs: Object.values(selected),
      mappings,
    })
    ui.set({ modal: 'jobs' })
  }
  async function submitBundle() {
    if (!bundle.data) return
    let needsReview = false
    for (const entry of bundle.data.streams) {
      const d = detections[entry.ref.uri] || (await inspect(entry.ref))
      if (d.mapping && !d.knownProfile && !mappings[entry.ref.uri])
        needsReview = true
    }
    if (needsReview) {
      notify('Approve the stream mappings below, then import this run bundle.')
      return
    }
    let workspaceId = ui.workspaceId
    if (!workspaceId) {
      const workspace = await create.mutateAsync({ name })
      workspaceId = workspace.id
      ui.setWorkspace(workspaceId)
    }
    await addBundle.mutateAsync({ workspaceId, ref: bundle.data.ref, mappings })
    ui.set({ modal: 'jobs' })
  }
  return (
    <div className="dialog-body add-source">
      <div className="source-tabs">
        {(['local', 'huggingface', 'http'] as const).map((tab) => (
          <button
            key={tab}
            className={kind === tab ? 'active' : ''}
            onClick={() => {
              setKind(tab)
              setRoot(null)
              setSelected({})
              setUri('')
            }}
          >
            {tab === 'local' ? <FolderOpen size={14} /> : <Globe2 size={14} />}{' '}
            {tab === 'local'
              ? 'Local'
              : tab === 'huggingface'
                ? 'Hugging Face'
                : 'HTTP URL'}
          </button>
        ))}
      </div>
      {!ui.workspaceId && (
        <Field label="Workspace name">
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
      )}
      {kind === 'local' && (
        <div className="source-local-actions">
          <Button
            variant="secondary"
            onClick={() => void pick(false).catch((e) => notify(String(e)))}
          >
            Open file
          </Button>
          <Button
            variant="secondary"
            onClick={() => void pick(true).catch((e) => notify(String(e)))}
          >
            Open directory
          </Button>
        </div>
      )}
      <Field
        label={
          kind === 'huggingface'
            ? 'Repository or Hugging Face URL'
            : kind === 'local'
              ? 'Local path'
              : 'File URL or directory manifest'
        }
      >
        <input
          autoFocus
          value={uri}
          placeholder={
            kind === 'huggingface'
              ? 'aisa-group/instrumental-choices-agent-traces'
              : kind === 'local'
                ? '/Users/you/research/runs'
                : 'https://example.org/traces/manifest.json'
          }
          onChange={(e) => setUri(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && uri)
              void open().catch((e) => notify(String(e)))
          }}
        />
      </Field>
      {kind === 'huggingface' && (
        <div className="form-grid">
          <Field label="Repository type">
            <select
              value={repoType}
              onChange={(e) => setRepoType(e.target.value)}
            >
              <option value="dataset">Dataset</option>
              <option value="model">Model</option>
              <option value="space">Space</option>
            </select>
          </Field>
          <Field label="Revision">
            <input
              value={revision}
              onChange={(e) => setRevision(e.target.value)}
            />
          </Field>
        </div>
      )}
      <div className="source-connect">
        <span className="muted small">
          {kind === 'huggingface'
            ? 'Uses standard Hugging Face login. Connecting retrieves repository metadata only.'
            : 'Original source files remain unchanged.'}
        </span>
        <Button
          disabled={!uri || connect.isPending}
          onClick={() => void open().catch((e) => notify(String(e)))}
        >
          {connect.isPending ? 'Connecting…' : 'Connect'}
          <ArrowRight size={13} />
        </Button>
      </div>
      {root && (
        <>
          <div className="source-location">
            <strong>{String(root.ref.metadata.repoId || root.name)}</strong>
            {root.ref.revision && (
              <code>revision {root.ref.revision.slice(0, 12)}</code>
            )}
            {root.ref.metadata.offlineMetadata === true && (
              <span>Cached metadata · offline</span>
            )}
          </div>
          {current?.isDirectory && (
            <div className="source-browser-toolbar">
              <button
                disabled={!trail.length}
                onClick={() => {
                  setTrail((t) => t.slice(0, -1))
                  setSearch('')
                }}
              >
                <ArrowLeft size={14} />
              </button>
              <span>{current.path || current.name}</span>
              <div className="search-input">
                <Search size={12} />
                <input
                  placeholder="Search filenames in this subtree…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>
          )}
          {current?.isDirectory && (
            <Button
              variant="ghost"
              size="sm"
              disabled={bundle.isPending}
              onClick={() => bundle.mutate({ ref: current.ref })}
            >
              Detect run bundle in this directory
            </Button>
          )}
          {bundle.data && (
            <div className="bundle-preview">
              <h4>Proposed run bundle</h4>
              <p>
                {bundle.data.streams.length} possible agent streams ·{' '}
                {bundle.data.scores.length} score files ·{' '}
                {bundle.data.configs.length} configuration files ·{' '}
                {bundle.data.artifacts.length} artifact directories
              </p>
              {(['streams', 'scores', 'configs', 'artifacts'] as const).map(
                (category) => (
                  <div key={category}>
                    <strong>{category}</strong>
                    <span>
                      {bundle.data![category].map((e) => e.name).join(', ') ||
                        'None'}
                    </span>
                  </div>
                ),
              )}
              <Button
                variant="secondary"
                disabled={!bundle.data.streams.length || addBundle.isPending}
                onClick={() =>
                  void submitBundle().catch((e) => notify(String(e)))
                }
              >
                Review & import as one run
              </Button>
            </div>
          )}
          {entries.isLoading && current?.isDirectory && (
            <Loading text="Listing source metadata…" />
          )}
          {entries.error && <ErrorState error={entries.error} />}
          <SourceFiles
            entries={items}
            selected={selected}
            detections={detections}
            onOpen={(entry) => {
              setTrail((t) => [...t, entry])
              setSearch('')
            }}
            onToggle={(entry) =>
              setSelected((old) => {
                const next = { ...old }
                if (next[entry.ref.uri]) delete next[entry.ref.uri]
                else next[entry.ref.uri] = entry.ref
                return next
              })
            }
          />
          <div className="source-selection">
            <span>
              {Object.keys(selected).length} selected ·{' '}
              {bytes(
                Object.values(selected).reduce(
                  (sum, r) => sum + (r.sizeBytes || 0),
                  0,
                ),
              )}{' '}
              source size
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={!Object.keys(selected).length || probing}
              onClick={() => void probe()}
            >
              {probing ? 'Inspecting headers…' : 'Detect selected formats'}
            </Button>
          </div>
          {Object.values(detections).map((d) => (
            <div className="source-detection" key={d.ref.uri}>
              <span className="tag">
                {d.detections[0]?.format.toUpperCase()}
              </span>
              <span>{d.ref.uri.split('/').at(-1)}</span>
              <small>
                {Math.round((d.detections[0]?.confidence || 0) * 100)}% ·{' '}
                {d.detections[0]?.reason}
              </small>
            </div>
          ))}
          {Object.values(detections)
            .filter((d) => !!d.mapping)
            .map((d) => (
              <MappingReview
                key={d.ref.uri + ':' + d.fingerprint}
                detection={d}
                approved={!!mappings[d.ref.uri] || !!d.knownProfile}
                onInvalidate={() => {
                  setMappings((old) => {
                    const next = { ...old }
                    delete next[d.ref.uri]
                    return next
                  })
                  setDetections((old) => ({
                    ...old,
                    [d.ref.uri]: { ...old[d.ref.uri], knownProfile: false },
                  }))
                }}
                onApprove={(value) =>
                  setMappings((old) => ({ ...old, [d.ref.uri]: value }))
                }
              />
            ))}
          <div className="source-import-note">
            <Check size={14} />
            <span>
              Only selected files are accessed. Inspect samples load on demand;
              selected event streams index progressively. Pin Offline is a
              separate action.
            </span>
          </div>
          <div className="form-actions">
            <span>Browse indexed events while imports continue.</span>
            <Button
              disabled={
                !Object.keys(selected).length ||
                add.isPending ||
                create.isPending
              }
              onClick={() => void submit().catch((e) => notify(String(e)))}
            >
              {kind === 'local' ? 'Add source' : 'Open remote'}
              <ArrowRight size={13} />
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

function SourceFiles({
  entries,
  selected,
  detections,
  onOpen,
  onToggle,
}: {
  entries: SourceEntry[]
  selected: Record<string, SourceRef>
  detections: Record<string, SourceDetection>
  onOpen: (e: SourceEntry) => void
  onToggle: (e: SourceEntry) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => ref.current,
    estimateSize: () => 42,
    overscan: 4,
  })
  return (
    <div className="source-file-list" ref={ref}>
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((v) => {
          const e = entries[v.index]
          return (
            <div
              className="source-file"
              key={e.ref.uri}
              style={{
                position: 'absolute',
                width: '100%',
                height: v.size,
                transform: `translateY(${v.start}px)`,
              }}
            >
              {e.isDirectory ? (
                <button className="source-folder" onClick={() => onOpen(e)}>
                  <Folder size={15} />
                  <span>{e.path || e.name}/</span>
                  <ArrowRight size={12} />
                </button>
              ) : (
                <>
                  <input
                    type="checkbox"
                    aria-label={`Select ${e.name}`}
                    checked={!!selected[e.ref.uri]}
                    onChange={() => onToggle(e)}
                  />
                  <File size={14} />
                  <span className="source-filename" title={e.path || e.name}>
                    {e.path || e.name}
                  </span>
                  <span className="tag">
                    {detections[
                      e.ref.uri
                    ]?.detections[0]?.format.toUpperCase() ||
                      e.formatHint ||
                      'File'}
                  </span>
                  <span>{bytes(e.sizeBytes)}</span>
                  <span className="source-cache-state">
                    {e.cachedBytes
                      ? `${bytes(e.cachedBytes)} cached`
                      : 'Uncached'}
                  </span>
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
