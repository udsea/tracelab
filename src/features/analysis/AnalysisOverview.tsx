import { useMemo, useState } from 'react'
import { ArrowUpRight, Crosshair, Flag, GitBranch } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Empty, Loading } from '@/components/common/Primitives'
import { useUI, type AnalysisTab } from '@/stores/ui'
import type { AnalysisSignal } from '@/types/analysis'
import { useOverview, useSignals } from './queries'
import {
  deriveRunOverview,
  fmt,
  type FamilySummary,
  type LaneSummary,
  type Moment,
} from './overview'
import { channelLabels, sourceLabel } from './channels'

const plural = (n: number, one: string, many = `${one}s`) =>
  `${n} ${n === 1 ? one : many}`
const notRun: [string, string, AnalysisTab][] = [
  ['llm', 'Semantic detectors', 'signals/semantic'],
  ['rule', 'Rules', 'signals/rules'],
  ['statistical', 'Statistics', 'signals/statistical'],
]

export function AnalysisOverview() {
  const ui = useUI()
  const overview = useOverview(ui.trajectoryId)
  const signals = useSignals(ui.trajectoryId)
  const [showAll, setShowAll] = useState(false)
  const [allMoments, setAllMoments] = useState(false)
  const summary = useMemo(
    () => deriveRunOverview(signals.data ?? [], overview.data?.outline ?? []),
    [signals.data, overview.data?.outline],
  )
  const lastIndex = Math.max(
    1,
    (overview.data?.coordinates.points.length ?? 1) - 1,
  )
  if (!ui.trajectoryId)
    return <Empty title="Select a trajectory to see its analysis" />
  if (signals.isLoading) return <Loading text="Summarizing signals…" />
  const counts = overview.data?.eventCounts
  const annotations = summary.families
    .filter((f) => f.sourceType === 'human')
    .reduce((n, f) => n + f.lanes[0].count, 0)
  const forks = summary.families
    .filter((f) => f.sourceType === 'intervention')
    .reduce((n, f) => n + f.lanes[0].count, 0)
  const detectors = summary.families.filter(
    (f) => !['human', 'intervention'].includes(f.sourceType),
  ).length
  const missing = notRun.filter(([source]) => !summary.measured.has(source))
  const moments = allMoments ? summary.allMoments : summary.moments
  return (
    <div className="feature-page analysis-overview">
      <header className="overview-header">
        <div>
          <span className="eyebrow">RUN OVERVIEW</span>
          <h2>What the signals show</h2>
          <p className="overview-counts">
            {counts ? `${counts.research.toLocaleString()} research events · ` : ''}
            {plural(detectors, 'signal family', 'signal families')} ·{' '}
            {plural(annotations, 'annotation')} · {plural(forks, 'fork')}
          </p>
        </div>
        <p className="overview-caveat">
          Research heuristics, not validated ground truth. Each score is in its
          detector’s own units; scores are not comparable probabilities.
        </p>
      </header>
      {signals.error && <p className="inline-error">{signals.error.message}</p>}
      {!summary.total ? (
        <Empty title="No analysis signals for this run yet">
          Run a rule or statistical detector (local, no model calls) or
          configure a semantic detector.
          <span className="overview-empty-actions">
            {notRun.map(([, label, tab]) => (
              <Button key={tab} variant="outline" size="sm" onClick={() => ui.openAnalysis(tab)}>
                {label}
              </Button>
            ))}
          </span>
        </Empty>
      ) : (
        <>
          {moments.length > 0 && (
            <section className="overview-moments" aria-labelledby="moments-heading">
              <div className="detail-heading" id="moments-heading">
                IMPORTANT MOMENTS
                {summary.allMoments.length > summary.moments.length && (
                  <button className="text-button" onClick={() => setAllMoments(!allMoments)}>
                    {allMoments ? 'Show fewer' : `Show all ${summary.allMoments.length}`}
                  </button>
                )}
              </div>
              <ol>
                {moments.map((m, i) => (
                  <MomentRow key={`${m.kind}:${m.signalId ?? m.label}:${i}`} moment={m} />
                ))}
              </ol>
            </section>
          )}
          <div className="overview-families">
            {summary.families.map((family) => (
              <FamilyCard key={family.id} family={family} lastIndex={lastIndex} />
            ))}
          </div>
          {(summary.completedWithoutMatches.length > 0 || missing.length > 0) && (
            <div className="overview-footnotes">
              {summary.completedWithoutMatches.length > 0 && (
                <p>
                  <strong>Completed without matches:</strong>{' '}
                  {summary.completedWithoutMatches.join(', ')}. Not evidence that
                  the behaviour is absent.
                </p>
              )}
              {missing.length > 0 && (
                <p>
                  <strong>Not measured on this run:</strong>{' '}
                  {missing.map(([, label, tab], i) => (
                    <span key={tab}>
                      {i > 0 && ' · '}
                      <button className="text-button" onClick={() => ui.openAnalysis(tab)}>
                        {label}
                      </button>
                    </span>
                  ))}
                </p>
              )}
            </div>
          )}
        </>
      )}
      {summary.total > 0 && (
        <section className="overview-raw">
          <button
            className="text-button"
            aria-expanded={showAll}
            onClick={() => setShowAll(!showAll)}
          >
            {showAll ? 'Hide measurements' : `Show all measurements (${summary.total})`}
          </button>
          {showAll && <SignalList rows={signals.data ?? []} />}
        </section>
      )}
    </div>
  )
}

function MomentRow({ moment }: { moment: Moment }) {
  const ui = useUI()
  const Icon =
    moment.kind === 'annotation' ? Flag : moment.kind === 'fork' ? GitBranch : Crosshair
  return (
    <li className={`overview-moment moment-${moment.kind}`}>
      <button
        className="moment-jump"
        onClick={() => ui.jump(moment.index)}
        title={`Open event #${moment.index} in the explorer`}
      >
        <span className="moment-index">#{moment.index}</span>
        <Icon size={12} aria-hidden />
        <span>
          <strong>{moment.label}</strong>
          <small>{moment.detail}</small>
        </span>
      </button>
      {moment.signalId && (
        <Button
          variant="ghost"
          size="icon"
          title="Inspect evidence"
          aria-label={`Inspect evidence for ${moment.label}`}
          onClick={() => ui.set({ signalId: moment.signalId })}
        >
          <ArrowUpRight size={13} />
        </Button>
      )}
    </li>
  )
}

function FamilyCard({
  family,
  lastIndex,
}: {
  family: FamilySummary
  lastIndex: number
}) {
  return (
    <article className="overview-family" aria-label={family.name}>
      <header>
        <h3>{family.name}</h3>
        <span className="tag">
          {sourceLabel(family.sourceType)} · {channelLabels[family.channel]}
        </span>
      </header>
      {family.lanes.map((lane) => (
        <LaneBlock
          key={lane.id}
          lane={lane}
          showName={family.lanes.length > 1}
          lastIndex={lastIndex}
        />
      ))}
    </article>
  )
}

function LaneBlock({
  lane,
  showName,
  lastIndex,
}: {
  lane: LaneSummary
  showName: boolean
  lastIndex: number
}) {
  const ui = useUI()
  return (
    <div className="overview-lane">
      {showName && <h4>{lane.name}</h4>}
      <p className="overview-headline">{lane.headline}</p>
      {lane.series.length > 1 && (
        <Sparkline lane={lane} lastIndex={lastIndex} />
      )}
      {lane.facts.length > 0 && (
        <dl className="overview-facts">
          {lane.facts.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {lane.kind !== 'series' && lane.moments.length > 1 && (
        <ul className="overview-lane-moments">
          {lane.moments.slice(0, 3).map((m, i) => (
            <li key={i}>
              <button onClick={() => ui.jump(m.index)}>
                #{m.index}
                {m.detail !== `#${m.index}` && <span>{m.detail || m.label}</span>}
              </button>
            </li>
          ))}
          {lane.moments.length > 3 && (
            <li className="muted small">+{lane.moments.length - 3} more in the timeline</li>
          )}
        </ul>
      )}
      <div className="overview-actions">
        {lane.evidenceSignalId && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => ui.set({ signalId: lane.evidenceSignalId })}
          >
            Inspect evidence
          </Button>
        )}
        {lane.focus && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => ui.focus(lane.focus!.start, lane.focus!.end, lane.name)}
          >
            Show in timeline
          </Button>
        )}
      </div>
    </div>
  )
}

/** Bounded inline chart; no chart library instance per card. */
export function Sparkline({
  lane,
  lastIndex,
}: {
  lane: LaneSummary
  lastIndex: number
}) {
  const width = 280,
    height = 46,
    pad = 3
  const scores = lane.series.map((p) => p.score)
  const low = Math.min(...scores),
    high = Math.max(...scores)
  const x = (index: number) => pad + (index / lastIndex) * (width - 2 * pad)
  const y = (score: number) =>
    height - pad - ((score - low) / Math.max(1e-9, high - low)) * (height - 2 * pad)
  const mid = (p: { start: number; end: number }) => (p.start + p.end) / 2
  const path = lane.series
    .map((p, i) => `${i ? 'L' : 'M'}${x(mid(p)).toFixed(1)},${y(p.score).toFixed(1)}`)
    .join(' ')
  return (
    <svg
      className="sparkline"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`${lane.name}: ${lane.series.length} measurements from ${fmt(low)} to ${fmt(high)}`}
    >
      {lane.rise && (
        <line
          className="sparkline-rise"
          x1={x(lane.rise.start)}
          x2={x(lane.rise.start)}
          y1={0}
          y2={height}
        />
      )}
      <path className="sparkline-line" d={path} />
      {lane.peak && (
        <circle
          className="sparkline-peak"
          cx={x(mid(lane.peak))}
          cy={y(lane.peak.score)}
          r={3}
        />
      )}
    </svg>
  )
}

export function SignalList({ rows }: { rows: AnalysisSignal[] }) {
  const ui = useUI()
  const [page, setPage] = useState(0)
  const offset = Math.min(
    page * 100,
    Math.max(0, Math.floor((rows.length - 1) / 100) * 100),
  )
  return (
    <div className="signal-summary-list">
      {rows.slice(offset, offset + 100).map((s) => (
        <button key={s.id} onClick={() => ui.set({ signalId: s.id })}>
          <span>
            {s.name}{' '}
            <small>
              {sourceLabel(s.sourceType)} · #{s.startEventIndex}–{s.endEventIndex}
            </small>
          </span>
          <strong>{s.score?.toFixed(2) ?? s.label ?? '—'}</strong>
        </button>
      ))}
      {rows.length > 100 && (
        <p>
          <button
            disabled={offset === 0}
            onClick={() => setPage(Math.max(0, page - 1))}
          >
            Previous signals
          </button>{' '}
          {offset + 1}–{Math.min(offset + 100, rows.length)} / {rows.length}{' '}
          <button
            disabled={offset + 100 >= rows.length}
            onClick={() => setPage(page + 1)}
          >
            Next signals
          </button>
        </p>
      )}
      {!rows.length && <p className="muted">No measurements here yet.</p>}
    </div>
  )
}
