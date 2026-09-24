import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dialog } from '@/components/ui/dialog'
import { useUI } from '@/stores/ui'
import { rpc } from '@/lib/api'
import { useTrajectory } from '@/hooks/queries'
import { useSignals } from './queries'
import type { AnalysisSignal, ArtifactRef } from '@/types/analysis'
import type { TrajectoryEvent } from '@/types/domain'
export function SignalInspector() {
  const ui = useUI(),
    trajectory = useTrajectory(ui.trajectoryId)
  const query = useQuery({
    queryKey: ['signal', ui.trajectoryId, ui.signalId],
    queryFn: () =>
      rpc<{ signal: AnalysisSignal; artifact: ArtifactRef | null }>(
        'analysis.signal',
        { trajectoryId: ui.trajectoryId, id: ui.signalId },
      ),
    enabled: !!ui.signalId && !!ui.trajectoryId,
  })
  const s = query.data?.signal,
    output = s?.metadata.output as
      | {
          rationale?: string
          counterevidenceEventIds?: string[]
          alternativeExplanations?: string[]
        }
      | undefined
  const fork = (index: number) => {
    ui.jump(
      Math.max(
        0,
        Math.min((trajectory.data?.trajectory.eventCount ?? 1) - 1, index),
      ),
    )
    ui.set({ signalId: null, modal: 'fork' })
  }
  return (
    <Dialog
      open={!!ui.signalId}
      onClose={() => ui.set({ signalId: null })}
      title={s?.name ?? 'Analysis signal'}
      description="Research heuristic · inspect evidence and alternative explanations"
      wide
    >
      <div className="dialog-body">
        {query.error && <p className="inline-error">{query.error.message}</p>}
        {s && (
          <>
            <div className="evidence-summary">
              <strong>{s.score?.toFixed(3) ?? s.label ?? 'Unscored'}</strong>
              <span>
                {s.sourceType} · {s.channel.replace('_', ' ')} · #
                {s.startEventIndex}–{s.endEventIndex}
              </span>
            </div>
            <button
              onClick={() => {
                ui.focus(s.startEventIndex, s.endEventIndex, s.name)
                ui.set({ signalId: null })
              }}
            >
              Focus receptive range
            </button>
            <p>{output?.rationale ?? String(s.metadata.note ?? '')}</p>
            <h4>Evidence</h4>
            <EvidenceIds ids={s.evidenceEventIds} />
            {!!output?.counterevidenceEventIds?.length && (
              <>
                <h4>Counterevidence</h4>
                <EvidenceIds ids={output.counterevidenceEventIds} />
              </>
            )}
            {output?.alternativeExplanations?.map((a, i) => (
              <p key={i}>Alternative: {a}</p>
            ))}
            {query.data?.artifact && (
              <>
                <h4>Artifact reference</h4>
                <pre>{JSON.stringify(query.data.artifact, null, 2)}</pre>
              </>
            )}
            <details
              className="raw-details"
              open={s.sourceType === 'statistical'}
            >
              <summary>Measurement / before and after statistics</summary>
              <pre>{JSON.stringify(s.metadata, null, 2)}</pre>
            </details>
            <details className="raw-details">
              <summary>
                Exact definition, inputs, prompt and raw provenance
              </summary>
              <pre>{JSON.stringify(s.provenance, null, 2)}</pre>
            </details>
            {trajectory.data?.capabilities.contextOnly && (
              <div className="form-actions">
                <button onClick={() => fork(s.startEventIndex - 1)}>
                  Fork before signal
                </button>
                <button
                  onClick={() =>
                    fork(
                      typeof s.metadata.peakEventIndex === 'number'
                        ? s.metadata.peakEventIndex
                        : s.startEventIndex,
                    )
                  }
                >
                  {typeof s.metadata.peakEventIndex === 'number'
                    ? 'Fork at peak'
                    : 'Fork at signal start'}
                </button>
                <button onClick={() => fork(s.endEventIndex + 1)}>
                  Fork after signal
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </Dialog>
  )
}
function EvidenceIds({ ids }: { ids: string[] }) {
  const ui = useUI()
  const [page, setPage] = useState(0)
  const offset = Math.min(
    page * 30,
    Math.max(0, Math.floor((ids.length - 1) / 30) * 30),
  )
  const query = useQuery({
    queryKey: ['signal-evidence', ids.slice(offset, offset + 30)],
    queryFn: () =>
      Promise.all(
        ids
          .slice(offset, offset + 30)
          .map((id) => rpc<{ event: TrajectoryEvent }>('events.get', { id })),
      ),
    enabled: ids.length > 0,
  })
  return (
    <div className="evidence-list">
      {query.data?.map(({ event }) => (
        <button
          className="evidence-link"
          key={event.id}
          onClick={() => {
            ui.jump(event.index)
            ui.set({ signalId: null })
          }}
        >
          <strong>#{event.index}</strong>
          <p>
            {event.content?.slice(0, 260) || event.tool?.name || event.type}
          </p>
        </button>
      ))}
      {ids.length > 30 && (
        <small>
          <button
            disabled={offset === 0}
            onClick={() => setPage(Math.max(0, page - 1))}
          >
            Previous evidence
          </button>
          {offset + 1}–{Math.min(offset + 30, ids.length)} of {ids.length}
          <button
            disabled={offset + 30 >= ids.length}
            onClick={() => setPage(page + 1)}
          >
            Next evidence
          </button>
        </small>
      )}
      {!ids.length && (
        <p>No point evidence supplied; inspect the declared range.</p>
      )}
    </div>
  )
}
export function AnalysisStack() {
  const ui = useUI(),
    query = useSignals(ui.trajectoryId)
  const rows =
    query.data?.filter(
      (s) =>
        s.startEventIndex <= ui.selectedIndex &&
        s.endEventIndex >= ui.selectedIndex,
    ) ?? []
  return (
    <section className="analysis-stack">
      <h4>Analysis stack · #{ui.selectedIndex}</h4>
      {(['BLACK_BOX', 'GRAY_BOX', 'WHITE_BOX'] as const).map((channel) => (
        <div key={channel}>
          <small>{channel.replace('_', ' ')}</small>
          {rows
            .filter((s) => s.channel === channel)
            .map((s) => (
              <button key={s.id} onClick={() => ui.set({ signalId: s.id })}>
                {s.name}
                <strong>{s.score?.toFixed(2) ?? s.label ?? '—'}</strong>
              </button>
            ))}
          {!rows.some((s) => s.channel === channel) && (
            <p className="muted">No measurements available.</p>
          )}
        </div>
      ))}
    </section>
  )
}
