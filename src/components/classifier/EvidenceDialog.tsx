import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, Braces, Clock3, Fingerprint } from 'lucide-react'
import { Dialog } from '@/components/ui/dialog'
import { Loading, ErrorState } from '@/components/common/Primitives'
import { rpc } from '@/lib/api'
import { json } from '@/lib/utils'
import { useClassifiers } from '@/hooks/queries'
import { useUI } from '@/stores/ui'
import type { ClassifierResult, TrajectoryEvent } from '@/types/domain'
function EvidenceLink({ id }: { id: string }) {
  const ui = useUI()
  const query = useQuery({
    queryKey: ['event', id],
    queryFn: () => rpc<{ event: TrajectoryEvent }>('events.get', { id }),
  })
  const event = query.data?.event
  return (
    <button
      className="evidence-link"
      onClick={() => {
        if (event) {
          if (ui.trajectoryId !== event.trajectoryId)
            ui.selectTrajectory(event.trajectoryId)
          ui.jump(event.index)
          ui.set({ resultId: null })
        }
      }}
    >
      <span>
        #{event?.index ?? '…'}
        <ArrowUpRight size={12} />
      </span>
      <p>{event?.content?.slice(0, 260) || 'Loading evidence event…'}</p>
    </button>
  )
}
export function EvidenceDialog() {
  const { resultId, set } = useUI()
  const definitions = useClassifiers()
  const result = useQuery({
    queryKey: ['result', resultId],
    queryFn: () => rpc<ClassifierResult>('results.get', { id: resultId }),
    enabled: !!resultId,
  })
  const data = result.data
  return (
    <Dialog
      open={!!resultId}
      onClose={() => set({ resultId: null })}
      title={
        definitions.data?.find((d) => d.id === data?.classifierId)?.name ||
        'Classifier evidence'
      }
      description="Trace the signal back to its source events."
      wide
    >
      {result.isLoading && <Loading text="Loading provenance…" />}
      {result.error && <ErrorState error={result.error} />}
      {data && (
        <div className="dialog-body">
          <div className="evidence-summary">
            <strong>{data.output?.score?.toFixed(2) ?? '—'}</strong>
            <div>
              <span>
                {data.output?.label ||
                  (data.error ? 'Classifier error' : 'Classifier result')}
              </span>
              <small>
                Events #{data.startEventIndex}–{data.endEventIndex}
                {data.cached ? ' · reused from cache' : ''}
              </small>
            </div>
            <span className="tag">
              {data.provenance?.synthetic ? 'SYNTHETIC' : 'MODEL OUTPUT'}
            </span>
          </div>
          {data.error && <div className="inline-error">{data.error}</div>}
          <h4>Rationale</h4>
          <p className="rationale">
            {data.output?.rationale || 'No rationale returned.'}
          </p>
          <h4>Evidence events</h4>
          <div className="evidence-list">
            {data.output?.evidenceEventIds.map((id) => (
              <EvidenceLink key={id} id={id} />
            ))}
          </div>
          {!data.output?.evidenceEventIds.length && (
            <p className="muted">No evidence events cited.</p>
          )}
          <div className="provenance-meta">
            <span>
              <Clock3 size={12} />
              {new Date(data.createdAt).toLocaleString()}
            </span>
            <span>
              <Fingerprint size={12} />
              {data.classifierId}
            </span>
          </div>
          <details className="raw-details">
            <summary>
              <Braces size={13} />
              Exact prompt & reproducibility record
            </summary>
            <pre>{json(data.provenance)}</pre>
          </details>
          <details className="raw-details">
            <summary>Raw result JSON</summary>
            <pre>{json(data)}</pre>
          </details>
        </div>
      )}
    </Dialog>
  )
}
