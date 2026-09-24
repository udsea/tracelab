import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Info } from 'lucide-react'
import { channelHelp, channelLabels, sourceLabel } from './channels'
import { humanize } from './overview'
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
                {sourceLabel(s.sourceType)} · {channelLabels[s.channel]} · #
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
/** One row per lane: overlapping rolling windows collapse to the one centred nearest the event. */
export function coveringSignals(signals: AnalysisSignal[], index: number) {
  const best = new Map<string, AnalysisSignal>()
  for (const s of signals) {
    if (s.startEventIndex > index || s.endEventIndex < index) continue
    const lane = String(s.metadata.laneId ?? s.name)
    const current = best.get(lane)
    const distance = (x: AnalysisSignal) =>
      Math.abs((x.startEventIndex + x.endEventIndex) / 2 - index)
    const width = (x: AnalysisSignal) => x.endEventIndex - x.startEventIndex
    if (
      !current ||
      distance(s) < distance(current) ||
      (distance(s) === distance(current) && width(s) < width(current))
    )
      best.set(lane, s)
  }
  return [...best.values()]
}
export function AnalysisStack() {
  const ui = useUI(),
    query = useSignals(ui.trajectoryId)
  const [help, setHelp] = useState(false)
  const rows = coveringSignals(query.data ?? [], ui.selectedIndex)
  // Only channels with measurements here; empty channels are not listed per event.
  const channels = (['BLACK_BOX', 'GRAY_BOX', 'WHITE_BOX'] as const).filter(
    (channel) => rows.some((s) => s.channel === channel),
  )
  return (
    <section className="analysis-stack" aria-label={`Analysis at event #${ui.selectedIndex}`}>
      <div className="analysis-stack-heading">
        <h4>Analysis at #{ui.selectedIndex}</h4>
        <button
          className="icon-button"
          aria-expanded={help}
          aria-label="What are black, gray and white box signals?"
          title="What are black, gray and white box signals?"
          onClick={() => setHelp(!help)}
        >
          <Info size={13} />
        </button>
      </div>
      {help && (
        <dl className="channel-help">
          {(['BLACK_BOX', 'GRAY_BOX', 'WHITE_BOX'] as const).map((c) => (
            <div key={c}>
              <dt>{channelLabels[c]}</dt>
              <dd>{channelHelp[c]}</dd>
            </div>
          ))}
        </dl>
      )}
      {!channels.length ? (
        <p className="muted analysis-empty">
          No analysis signals cover this event.
        </p>
      ) : (
        channels.map((channel) => (
          <div key={channel}>
            <small title={channelHelp[channel]}>{channelLabels[channel]}</small>
            {rows
              .filter((s) => s.channel === channel)
              .map((s) => (
                <button key={s.id} onClick={() => ui.set({ signalId: s.id })}>
                  {humanize(s.name)}
                  <strong>
                    {s.sourceType === 'human'
                      ? 'annotation'
                      : (s.score?.toFixed(2) ?? s.label ?? '—')}
                  </strong>
                </button>
              ))}
          </div>
        ))
      )}
    </section>
  )
}
