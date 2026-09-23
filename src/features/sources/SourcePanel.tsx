import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowUpRight,
  Check,
  CloudDownload,
  Database,
  RefreshCw,
  X,
} from 'lucide-react'
import { Dialog } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ErrorState, Loading } from '@/components/common/Primitives'
import { useAction } from '@/hooks/queries'
import { openNative, rpc } from '@/lib/api'
import { notify, useUI } from '@/stores/ui'
import {
  bytes,
  type CacheStats,
  type Capabilities,
  type SourceRef,
} from '@/types/sources'
import type { Job, Trajectory } from '@/types/domain'

interface SourceInfo {
  ref: SourceRef
  format: string
  importedAt: string
  cache: CacheStats
  indexState: string
  indexError?: string
  indexedEvents: number
  capabilities?: Capabilities
  url?: string
}

export function SourceBadge({ trajectory }: { trajectory: Trajectory }) {
  const [open, setOpen] = useState(false)
  const format = String(
    trajectory.metadata.importFormat || trajectory.metadata.format || 'inspect',
  )
  const provider = trajectory.sourceRef?.kind || 'local'
  return (
    <>
      <button
        className="source-badge"
        onClick={() => setOpen(true)}
        title="Source provenance and offline availability"
      >
        <Database size={11} />
        {format.toUpperCase()} ·{' '}
        {provider === 'huggingface' ? 'HF' : provider.toUpperCase()}
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Source & provenance"
        description="Source identity, cached bytes, and verified capabilities."
        wide
      >
        {open && <SourcePanel trajectoryId={trajectory.id} />}
      </Dialog>
    </>
  )
}

function SourcePanel({ trajectoryId }: { trajectoryId: string }) {
  const ui = useUI()
  const info = useQuery({
    queryKey: ['source-info', trajectoryId],
    queryFn: () => rpc<SourceInfo>('sources.info', { trajectoryId }),
    refetchInterval: 3000,
  })
  const pin = useAction<Job>('sources.pin', ['jobs', 'source-info', 'cache'])
  const clear = useAction('sources.clear', ['source-info', 'cache'])
  const retry = useAction<Job>('sources.retry', ['jobs', 'trajectory'])
  const freshness = useAction<{
    imported: string
    current: string
    changed: boolean
    offline: boolean
    ref: SourceRef
  }>('sources.freshness')
  const add = useAction<Job>('sources.add', [
    'jobs',
    'experiments',
    'trajectories',
  ])
  if (info.isLoading) return <Loading />
  if (info.error) return <ErrorState error={info.error} />
  if (!info.data) return null
  const d = info.data
  return (
    <div className="dialog-body source-provenance">
      <dl>
        <dt>Format</dt>
        <dd>{d.format.toUpperCase()}</dd>
        <dt>Provider</dt>
        <dd>{d.ref.kind === 'huggingface' ? 'Hugging Face' : d.ref.kind}</dd>
        {!!d.ref.metadata.repoId && (
          <>
            <dt>Repository</dt>
            <dd>{String(d.ref.metadata.repoId)}</dd>
          </>
        )}
        {d.ref.revision && (
          <>
            <dt>Pinned revision</dt>
            <dd>
              <code>{d.ref.revision}</code>
            </dd>
          </>
        )}
        <dt>Path</dt>
        <dd>{String(d.ref.metadata.path || d.ref.uri)}</dd>
        <dt>Remote size</dt>
        <dd>{bytes(d.ref.sizeBytes)}</dd>
        <dt>Cached raw bytes</dt>
        <dd>
          {bytes(d.cache.usageBytes)} · {bytes(d.cache.pinnedBytes)} pinned
        </dd>
        <dt>Local normalized index</dt>
        <dd>
          {d.indexedEvents.toLocaleString()} events ·{' '}
          {d.indexState.replaceAll('_', ' ').toLowerCase()}
        </dd>
        <dt>Imported</dt>
        <dd>{new Date(d.importedAt).toLocaleString()}</dd>
        {d.ref.checksum && (
          <>
            <dt>Checksum</dt>
            <dd>
              <code>{d.ref.checksum}</code>
            </dd>
          </>
        )}
        {d.ref.etag && (
          <>
            <dt>ETag</dt>
            <dd>
              <code>{d.ref.etag}</code>
            </dd>
          </>
        )}
      </dl>
      {d.indexError && (
        <div className="inline-error">
          {d.indexError}
          <Button
            variant="secondary"
            onClick={() => retry.mutate({ trajectoryId })}
          >
            Retry indexing
          </Button>
        </div>
      )}
      {d.capabilities && (
        <>
          <h4>Capabilities</h4>
          <div className="capability-grid">
            {Object.entries(d.capabilities)
              .filter(([key]) => key !== 'reason')
              .map(([key, value]) => (
                <span key={key}>
                  {value ? <Check size={12} /> : <X size={12} />}{' '}
                  {key.replace(/([A-Z])/g, ' $1')}
                </span>
              ))}
          </div>
          <p className="muted small">{d.capabilities.reason}</p>
        </>
      )}
      <div className="source-actions">
        {d.url && (
          <Button
            variant="secondary"
            onClick={() =>
              void openNative(d.url!).catch((e) => notify(String(e)))
            }
          >
            <ArrowUpRight size={13} />
            Open source
          </Button>
        )}
        {d.ref.kind !== 'local' && (
          <>
            <Button
              disabled={pin.isPending}
              onClick={() => pin.mutate({ ref: d.ref, trajectoryId })}
            >
              <CloudDownload size={13} />
              Pin offline
            </Button>
            <Button
              variant="ghost"
              disabled={clear.isPending}
              onClick={() => clear.mutate({ ref: d.ref, trajectoryId })}
            >
              Clear cached raw data
            </Button>
          </>
        )}
        {d.ref.kind === 'huggingface' && (
          <Button
            variant="ghost"
            disabled={freshness.isPending}
            onClick={() => freshness.mutate({ ref: d.ref })}
          >
            <RefreshCw size={12} />
            Check revision
          </Button>
        )}
      </div>
      <p className="muted small">
        Clearing the raw cache preserves normalized events, annotations,
        classifier results, and source provenance. Pinning downloads the
        selected file or run bundle and protects it from eviction.
      </p>
      {freshness.data && (
        <div className="source-revision">
          {freshness.data.offline ? (
            'Remote check unavailable; showing cached revision.'
          ) : freshness.data.changed ? (
            <>
              A newer revision is available:{' '}
              <code>{freshness.data.current.slice(0, 12)}</code>
              <Button
                size="sm"
                onClick={() =>
                  add.mutate({
                    workspaceId: ui.workspaceId,
                    refs: [freshness.data!.ref],
                  })
                }
              >
                Import new revision
              </Button>
              <span>Current experiment remains pinned.</span>
            </>
          ) : (
            'Already at the latest revision.'
          )}
        </div>
      )}
    </div>
  )
}

export function RemoteCacheSettings() {
  const query = useQuery({
    queryKey: ['cache'],
    queryFn: () => rpc<CacheStats>('cache.stats'),
  })
  const [maximum, setMaximum] = useState('20')
  const configure = useAction<CacheStats>('cache.configure', ['cache'])
  const clear = useAction<CacheStats>('cache.clear', ['cache', 'source-info'])
  return (
    <section className="remote-cache-settings">
      <h3>
        <Database size={15} />
        Remote cache
      </h3>
      {query.error && <ErrorState error={query.error} />}
      <p>
        {bytes(query.data?.usageBytes)} used · {bytes(query.data?.pinnedBytes)}{' '}
        pinned · limit {bytes(query.data?.maximumBytes)}
      </p>
      <div className="cache-controls">
        <label>
          Maximum size (GiB)
          <input
            type="number"
            min="0.02"
            step="1"
            value={maximum}
            onChange={(e) => setMaximum(e.target.value)}
          />
        </label>
        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            configure.mutate({ maximumBytes: Number(maximum) * 1024 ** 3 })
          }
        >
          Save limit
        </Button>
        <Button variant="ghost" size="sm" onClick={() => clear.mutate({})}>
          Clear unpinned cache
        </Button>
      </div>
      <p className="muted small">
        Least recently used eviction. Pinned sources and the research database
        are retained.
      </p>
    </section>
  )
}
