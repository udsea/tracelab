import { useUI } from '@/stores/ui'
import { useOverview } from './queries'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useRef, useState } from 'react'
import { useProviders, useAction } from '@/hooks/queries'
import type { Job } from '@/types/domain'
export function RunOutline() {
  const ui = useUI(),
    query = useOverview(ui.trajectoryId),
    ref = useRef<HTMLDivElement>(null)
  const providers = useProviders(),
    [provider, setProvider] = useState('openai'),
    [model, setModel] = useState(''),
    [interpret, setInterpret] = useState(false)
  const run = useAction<Job>('analysis.interpret', ['jobs'])
  const nodes = query.data?.outline ?? []
  const virtual = useVirtualizer({
    count: nodes.length,
    getScrollElement: () => ref.current,
    estimateSize: () => 73,
    overscan: 4,
  })
  return (
    <section className="run-outline">
      <div className="sidebar-heading">
        RUN OUTLINE{' '}
        <button
          onClick={() => ui.backRange()}
          disabled={!ui.rangeHistory.length}
        >
          Back
        </button>
      </div>
      <button
        className="phase-link"
        onClick={() =>
          ui.focus(
            0,
            Math.max(0, (query.data?.coordinates.points.length ?? 1) - 1),
            'All events',
          )
        }
      >
        All events
      </button>
      {query.isLoading && <p>Deriving recorded activity…</p>}
      {query.error && <p className="inline-error">{query.error.message}</p>}
      <div ref={ref} style={{ height: 320, overflow: 'auto' }}>
        <div style={{ height: virtual.getTotalSize(), position: 'relative' }}>
          {virtual.getVirtualItems().map((row) => {
            const n = nodes[row.index]
            return (
              <button
                key={n.id}
                className="outline-node"
                style={{
                  position: 'absolute',
                  top: 0,
                  transform: `translateY(${row.start}px)`,
                  height: row.size,
                  width: '100%',
                }}
                title={`${n.stats.agents.join(', ')} · ${n.stats.filesReferenced.length} file paths referenced`}
                onClick={() =>
                  ui.focus(n.startEventIndex, n.endEventIndex, n.label)
                }
              >
                <small>
                  {n.kind.toUpperCase()} · #{n.startEventIndex}–
                  {n.endEventIndex}
                </small>
                <strong>{n.label}</strong>
                <small>
                  {n.stats.eventCount} events · {n.stats.toolCalls} calls ·{' '}
                  {n.stats.errors} errors
                  {n.stats.durationMs != null
                    ? ` · ${Math.round(n.stats.durationMs / 1000)}s`
                    : ''}
                </small>
                <small>
                  {n.stats.agents.join(', ') || 'Agent identity unavailable'}
                </small>
              </button>
            )
          })}
        </div>
      </div>
      <button
        className="sidebar-text-action"
        onClick={() => setInterpret(!interpret)}
      >
        Interpret outline with LLM
      </button>
      {interpret && (
        <div style={{ padding: 12 }}>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            {providers.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <input
            aria-label="Outline model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="provider/model"
          />
          <small>
            Sends semantic event summaries to the selected provider.
          </small>
          <button
            disabled={!model || run.isPending}
            onClick={() =>
              run.mutate({ trajectoryId: ui.trajectoryId, provider, model })
            }
          >
            Generate interpreted outline
          </button>
        </div>
      )}
      <button
        className="sidebar-text-action"
        onClick={() => ui.set({ modal: 'segment' })}
      >
        Interpret / edit narrative phases
      </button>
    </section>
  )
}
