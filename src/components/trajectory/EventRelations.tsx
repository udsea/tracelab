import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, GitBranch } from 'lucide-react'
import { rpc } from '@/lib/api'
import { useUI } from '@/stores/ui'
import type { TrajectoryEvent } from '@/types/domain'

function ParentLink({ id }: { id: string }) {
  const query = useQuery({
    queryKey: ['event', id],
    queryFn: () => rpc<{ event: TrajectoryEvent }>('events.get', { id }),
    retry: false,
  })
  return (
    <button
      disabled={!query.data}
      title={
        query.error
          ? 'Referenced event has not been indexed, or is external to this source.'
          : id
      }
      onClick={() => {
        if (query.data) useUI.getState().jump(query.data.event.index)
      }}
    >
      <ArrowUpRight size={11} />
      {query.data
        ? `#${query.data.event.index} · ${query.data.event.content?.slice(0, 45) || query.data.event.type}`
        : 'Referenced event · unavailable'}
    </button>
  )
}
export function EventRelations({ event }: { event: TrajectoryEvent }) {
  if (!event.metadata.structuralKind && !event.metadata.agentId) return null
  return (
    <section className="event-relations">
      <h4>
        <GitBranch size={12} />
        Structure
      </h4>
      {!!event.metadata.agentId && (
        <p>
          Agent <code>{String(event.metadata.agentId)}</code>
        </p>
      )}
      {!!event.metadata.structuralKind && (
        <p>
          {String(event.metadata.structuralKind)}{' '}
          {String(event.metadata.scopePhase || event.metadata.spanKind || '')}
        </p>
      )}
      {typeof event.metadata.durationMs === 'number' && (
        <p>{event.metadata.durationMs.toFixed(1)} ms</p>
      )}
      {event.parentEventIds.length > 0 && (
        <>
          <span className="muted small">Parent events</span>
          {event.parentEventIds.map((id) => (
            <ParentLink key={id} id={id} />
          ))}
        </>
      )}
    </section>
  )
}
