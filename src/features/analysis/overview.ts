import type { AnalysisSignal, OutlineNode } from '@/types/analysis'

/**
 * Deterministic run summaries derived from compact signal summaries.
 * Descriptions stay in each detector's own units: scores from different
 * detectors are not calibrated probabilities and are never compared here.
 */

export interface SeriesPoint {
  start: number
  end: number
  score: number
  signalId: string
}
export interface Moment {
  index: number
  end: number
  label: string
  detail: string
  kind: 'match' | 'annotation' | 'fork' | 'peak' | 'rise' | 'change' | 'recorded'
  signalId?: string
}
export interface LaneSummary {
  id: string
  name: string
  kind: 'series' | 'matches' | 'annotations' | 'forks' | 'observations'
  count: number
  headline: string
  facts: [string, string][]
  series: SeriesPoint[]
  peak?: SeriesPoint
  rise?: SeriesPoint
  moments: Moment[]
  evidenceSignalId?: string
  focus?: { start: number; end: number }
}
export interface FamilySummary {
  id: string
  name: string
  sourceType: string
  channel: AnalysisSignal['channel']
  lanes: LaneSummary[]
}
export interface RunOverview {
  families: FamilySummary[]
  /** Highest-priority moments, in event order. */
  moments: Moment[]
  allMoments: Moment[]
  completedWithoutMatches: string[]
  measured: Set<string>
  total: number
}

const SERIES_SOURCES = new Set([
  'llm',
  'statistical',
  'probe',
  'sae',
  'logit',
  'custom',
])
const SPARK_POINTS = 120
export const fmt = (value: number) =>
  Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(2)
/** Machine labels such as `repeated_tool_loop` read as prose. */
export const humanize = (value: string) => {
  const text = value.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}
const words = (value: string) =>
  value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/s\b/g, '').trim()
const same = (a: string, b: string) => words(a) === words(b)
const range = (s: { start: number; end: number }) =>
  s.start === s.end ? `#${s.start}` : `#${s.start}–${s.end}`

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

/** Bounded series for compact charts: keep each bucket's largest value. */
export function downsample(points: SeriesPoint[], limit = SPARK_POINTS) {
  if (points.length <= limit) return points
  const size = points.length / limit
  const output: SeriesPoint[] = []
  for (let i = 0; i < limit; i++) {
    const bucket = points.slice(Math.floor(i * size), Math.floor((i + 1) * size))
    if (bucket.length)
      output.push(bucket.reduce((a, b) => (b.score > a.score ? b : a)))
  }
  return output
}

export function summarizeSeries(
  name: string,
  signals: AnalysisSignal[],
): Omit<LaneSummary, 'id' | 'kind'> {
  const points = signals
    .filter((s) => typeof s.score === 'number' && Number.isFinite(s.score))
    .map((s) => ({
      start: s.startEventIndex,
      end: s.endEventIndex,
      score: s.score as number,
      signalId: s.id,
    }))
    .sort((a, b) => a.start - b.start || a.end - b.end)
  if (!points.length)
    return {
      name,
      count: signals.length,
      headline: `${signals.length} labelled measurements; no numeric scores to trend.`,
      facts: [],
      series: [],
      moments: [],
    }
  const scores = points.map((p) => p.score)
  const baseline = median(scores.slice(0, Math.min(3, scores.length)))
  const peak = points.reduce((a, b) => (b.score > a.score ? b : a))
  const low = Math.min(...scores)
  const spread = peak.score - low
  const final = points.at(-1)!
  const moments: Moment[] = [
    {
      index: peak.start,
      end: peak.end,
      label: `${name} peak ${fmt(peak.score)}`,
      detail: `Highest emitted score, ${range(peak)}`,
      kind: 'peak',
      signalId: peak.signalId,
    },
  ]
  const facts: [string, string][] = [
    ['Peak', `${fmt(peak.score)} at ${range(peak)}`],
    ['Final window', `${fmt(final.score)} at ${range(final)}`],
  ]
  if (points.length < 3 || spread < 1e-9) {
    return {
      name,
      count: signals.length,
      headline:
        spread < 1e-9
          ? `Constant at ${fmt(peak.score)} across ${points.length} measurements.`
          : `${points.length} measurements between ${fmt(low)} and ${fmt(peak.score)}.`,
      facts,
      series: downsample(points),
      peak,
      moments,
      evidenceSignalId: peak.signalId,
      focus: { start: peak.start, end: peak.end },
    }
  }
  // A rise is the first window at least halfway from the early level to the peak.
  const threshold = baseline + 0.5 * (peak.score - baseline)
  const rise =
    peak.score - baseline >= 0.5 * spread
      ? points.find((p) => p.score >= threshold && p.start <= peak.start)
      : undefined
  let change = { delta: 0, at: points[0] }
  for (let i = 1; i < points.length; i++) {
    const delta = points[i].score - points[i - 1].score
    if (Math.abs(delta) > Math.abs(change.delta))
      change = { delta, at: points[i] }
  }
  let intervals = 0
  if (rise)
    points.forEach((p, i) => {
      if (p.score >= threshold && (i === 0 || points[i - 1].score < threshold))
        intervals++
    })
  const relative = (final.score - baseline) / spread
  let headline: string
  if (rise && relative >= 0.5)
    headline = `Starts near ${fmt(baseline)}, rises around ${range(rise)} and peaks at ${fmt(peak.score)} (${range(peak)}). Final window ${fmt(final.score)}.`
  else if (rise)
    headline = `Peaks at ${fmt(peak.score)} around ${range(peak)}, then returns toward ${fmt(final.score)}.`
  else if (relative <= -0.5)
    headline = `Starts near ${fmt(baseline)} and falls to ${fmt(final.score)} by ${range(final)}.`
  else
    headline = `Varies between ${fmt(low)} and ${fmt(peak.score)} with no sustained rise.`
  if (rise && rise.signalId !== peak.signalId)
    moments.unshift({
      index: rise.start,
      end: rise.end,
      label: `${name} rises`,
      detail: `Halfway from the early level to the peak · ${range(rise)}`,
      kind: 'rise',
      signalId: rise.signalId,
    })
  if (change.delta && change.at.signalId !== peak.signalId)
    moments.push({
      index: change.at.start,
      end: change.at.end,
      label: `Largest ${name} change`,
      detail: `${change.delta > 0 ? '+' : ''}${fmt(change.delta)} between consecutive measurements`,
      kind: 'change',
      signalId: change.at.signalId,
    })
  if (rise) facts.unshift(['First rise', range(rise)])
  facts.push([
    'Largest change',
    `${change.delta > 0 ? '+' : ''}${fmt(change.delta)} at ${range(change.at)}`,
  ])
  if (rise) facts.push(['Elevated intervals', String(intervals)])
  return {
    name,
    count: signals.length,
    headline,
    facts,
    series: downsample(points),
    peak,
    rise,
    moments,
    evidenceSignalId: peak.signalId,
    focus: rise
      ? { start: rise.start, end: Math.max(peak.end, rise.end) }
      : { start: peak.start, end: peak.end },
  }
}

function summarizeMatches(
  name: string,
  signals: AnalysisSignal[],
): Omit<LaneSummary, 'id' | 'kind'> {
  const matches = [...signals].sort(
    (a, b) => a.startEventIndex - b.startEventIndex,
  )
  const first = matches[0]
  return {
    name,
    count: matches.length,
    headline:
      matches.length === 1
        ? `1 match at ${range({ start: first.startEventIndex, end: first.endEventIndex })}.`
        : `${matches.length} matches, first at #${first.startEventIndex}.`,
    facts:
      matches.length > 1
        ? [['Last match', `#${matches.at(-1)!.startEventIndex}`]]
        : [],
    series: [],
    moments: matches.map((s) => ({
      index: s.startEventIndex,
      end: s.endEventIndex,
      label: name,
      detail: same(s.label ?? '', name)
        ? range({ start: s.startEventIndex, end: s.endEventIndex })
        : `${humanize(s.label ?? 'match')} · ${range({ start: s.startEventIndex, end: s.endEventIndex })}`,
      kind: 'match' as const,
      signalId: s.id,
    })),
    evidenceSignalId: first.id,
    focus: { start: first.startEventIndex, end: first.endEventIndex },
  }
}

const MOMENT_LIMIT = 8
const momentPriority: Moment['kind'][] = [
  'annotation',
  'match',
  'fork',
  'rise',
  'peak',
  'recorded',
  'change',
]
const laneKey = (s: AnalysisSignal) => String(s.metadata.laneId ?? s.name)
const familyKey = (s: AnalysisSignal) =>
  String(s.provenance.detectorId ?? s.metadata.laneId ?? s.name)
const familyOrder = [
  'llm',
  'probe',
  'sae',
  'logit',
  'custom',
  'rule',
  'statistical',
  'contrastive',
  'environment',
  'human',
  'intervention',
]

export function deriveRunOverview(
  signals: AnalysisSignal[],
  outline: OutlineNode[] = [],
): RunOverview {
  const families = new Map<string, AnalysisSignal[]>()
  const completedWithoutMatches: string[] = []
  const measured = new Set<string>()
  for (const s of signals) {
    if (s.label === 'no_matches') {
      measured.add(s.sourceType)
      if (!completedWithoutMatches.includes(s.name))
        completedWithoutMatches.push(s.name)
      continue
    }
    measured.add(s.sourceType)
    const key = familyKey(s)
    families.set(key, [...(families.get(key) ?? []), s])
  }
  const summaries: FamilySummary[] = []
  for (const [id, rows] of families) {
    const lanes = new Map<string, AnalysisSignal[]>()
    for (const s of rows) lanes.set(laneKey(s), [...(lanes.get(laneKey(s)) ?? []), s])
    const sourceType = rows[0].sourceType
    summaries.push({
      id,
      name:
        sourceType === 'statistical'
          ? 'Behavioral statistics'
          : sourceType === 'human'
            ? 'Annotations'
            : rows[0].name,
      sourceType,
      channel: rows[0].channel,
      lanes: [...lanes].map(([laneId, laneRows]) => {
        const name = humanize(laneRows[0].name)
        if (sourceType === 'human')
          return {
            id: laneId,
            kind: 'annotations',
            name,
            count: laneRows.length,
            headline: `${laneRows.length} annotation${laneRows.length === 1 ? '' : 's'}.`,
            facts: [],
            series: [],
            moments: laneRows.map((s) => ({
              index: s.startEventIndex,
              end: s.endEventIndex,
              label: s.label ?? s.name,
              detail: `Annotation · ${range({ start: s.startEventIndex, end: s.endEventIndex })}`,
              kind: 'annotation',
              signalId: s.id,
            })),
            evidenceSignalId: laneRows[0].id,
          }
        if (sourceType === 'intervention')
          return {
            id: laneId,
            kind: 'forks',
            name: 'Forks',
            count: laneRows.length,
            headline: `${laneRows.length} fork${laneRows.length === 1 ? '' : 's'} from this run.`,
            facts: [],
            series: [],
            moments: laneRows.map((s) => ({
              index: s.startEventIndex,
              end: s.endEventIndex,
              label: 'Fork',
              detail: `Context-only fork · ${s.label ?? 'status unknown'}`,
              kind: 'fork',
              signalId: s.id,
            })),
          }
        if (sourceType === 'environment')
          return {
            id: laneId,
            kind: 'observations',
            ...summarizeMatches(name, laneRows),
            headline: `${laneRows.length} recorded environment observation${laneRows.length === 1 ? '' : 's'}, first at #${Math.min(...laneRows.map((s) => s.startEventIndex))}.`,
            facts: [],
            moments: [],
          }
        const numeric = laneRows.filter((s) => typeof s.score === 'number')
        if (SERIES_SOURCES.has(sourceType) && numeric.length >= 2)
          return { id: laneId, kind: 'series', ...summarizeSeries(name, laneRows) }
        return { id: laneId, kind: 'matches', ...summarizeMatches(name, laneRows) }
      }),
    })
  }
  summaries.sort(
    (a, b) =>
      familyOrder.indexOf(a.sourceType) - familyOrder.indexOf(b.sourceType) ||
      a.name.localeCompare(b.name),
  )
  // A few moments per lane keep the list readable; everything stays reachable per family.
  const laneOf = new Map<Moment, string>()
  const statistical = new Set<Moment>()
  const allMoments = [
    ...summaries.flatMap((f) =>
      f.lanes.flatMap((l) => {
        const picked = l.moments.slice(
          0,
          l.kind !== 'series' ? 3 : f.sourceType === 'statistical' ? 1 : 2,
        )
        for (const m of picked) {
          laneOf.set(m, `${f.id}:${l.id}`)
          if (f.sourceType === 'statistical') statistical.add(m)
        }
        return picked
      }),
    ),
    ...outline
      .filter((n) => n.kind === 'moment')
      .slice(0, 3)
      .map((n) => ({
        index: n.startEventIndex,
        end: n.endEventIndex,
        label: n.label,
        detail: 'Recorded moment from the deterministic outline',
        kind: 'recorded' as const,
      })),
  ].sort((a, b) => a.index - b.index || a.end - b.end)
  // One moment per lane first, so a single busy detector cannot crowd out the rest.
  const ranked = allMoments.map((m, order) => ({
    m,
    order,
    lane: laneOf.get(m) ?? m.kind,
    rank:
      momentPriority.indexOf(m.kind) +
      (statistical.has(m) ? momentPriority.length : 0),
  }))
  const seen = new Set<string>()
  const firstPass = ranked
    .sort((a, b) => a.rank - b.rank || a.order - b.order)
    .filter((r) => !seen.has(r.lane) && !!seen.add(r.lane))
  const chosen = [
    ...firstPass,
    ...ranked.filter((r) => !firstPass.includes(r)),
  ].slice(0, MOMENT_LIMIT)
  const moments = chosen.sort((a, b) => a.order - b.order).map((r) => r.m)
  return {
    families: summaries,
    moments,
    allMoments,
    completedWithoutMatches,
    measured,
    total: signals.length,
  }
}
