import { ContrastiveSignals } from '@/features/analysis/ContrastiveSignals'
import { useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  ArrowDown,
  ArrowRight,
  Columns2,
  GitCompareArrows,
  Info,
  Layers3,
} from 'lucide-react'
import { useClassifiers, useExperiments } from '@/hooks/queries'
import { Button } from '@/components/ui/button'
import { TrajectoryPicker } from '@/components/trajectory/TrajectoryPicker'
import {
  Empty,
  ErrorState,
  Loading,
  Status,
} from '@/components/common/Primitives'
import { rpc } from '@/lib/api'
import { duration, number } from '@/lib/utils'
import { useUI } from '@/stores/ui'
import type { Filter, PairComparison, Trajectory } from '@/types/domain'
interface Group {
  experimentId?: string
  filters?: Filter[]
}
interface Aggregate {
  group: Group
  trajectories: number
  success: number
  successRate?: number
  errors: number
  meanTokens?: number
  scoredOutcomes: number
  classifiers: {
    classifierId: string
    meanScore: number
    aboveThreshold: number
    n: number
  }[]
}
export function ComparisonWorkspace() {
  const [tab, setTab] = useState('pair')
  return (
    <div className="feature-page compare-page">
      <div className="feature-heading">
        <div>
          <span className="eyebrow">COMPARISON WORKBENCH</span>
          <h1>Follow the divergence.</h1>
          <p>Compare the change in history with the change in behaviour.</p>
        </div>
        <div className="segmented-control">
          <button
            className={tab === 'pair' ? 'active' : ''}
            onClick={() => setTab('pair')}
          >
            <Columns2 size={13} />
            Trajectories
          </button>
          <button
            className={tab === 'groups' ? 'active' : ''}
            onClick={() => setTab('groups')}
          >
            <Layers3 size={13} />
            Experiments
          </button>
        </div>
      </div>
      {tab === 'pair' ? <PairView /> : <GroupView />}
    </div>
  )
}
function PairView() {
  const ui = useUI()
  const [left, setLeft] = useState(ui.trajectoryId || '')
  const [right, setRight] = useState(ui.comparisonRight || '')
  const [differencesOnly, setDifferencesOnly] = useState(false)
  const [matchField, setMatchField] = useState('sampleId')
  const candidates = useQuery({
    queryKey: ['matched-trajectories', left, matchField],
    queryFn: () =>
      rpc<Trajectory[]>('analysis.matchCandidates', {
        controlId: left,
        field: matchField,
      }),
    enabled: !!left,
  })
  const result = useQuery({
    queryKey: ['comparison', left, right],
    queryFn: () => rpc<PairComparison>('compare.pair', { left, right }),
    enabled: !!left && !!right && left !== right,
  })
  const data = result.data
  const rows = useMemo(
    () => data?.rows.filter((r) => !differencesOnly || r.changed) || [],
    [data, differencesOnly],
  )
  const ref = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => ref.current,
    estimateSize: () => 120,
    overscan: 4,
  })
  return (
    <>
      <div className="comparison-selectors">
        <label>
          <span>ORIGINAL</span>
          <TrajectoryPicker value={left} onChange={setLeft} exclude={right} />
        </label>
        <GitCompareArrows size={20} />
        <label>
          <span>COMPARISON</span>
          <TrajectoryPicker
            value={right}
            onChange={setRight}
            exclude={left}
            placeholder="Select trajectory or branch…"
          />
        </label>
      </div>
      <div className="comparison-selectors">
        <label>
          Match by
          <select
            value={matchField.startsWith('metadata.') ? 'metadata' : matchField}
            onChange={(e) =>
              setMatchField(
                e.target.value === 'metadata'
                  ? 'metadata.task_id'
                  : e.target.value,
              )
            }
          >
            <option value="sampleId">Sample ID</option>
            <option value="task">Task</option>
            <option value="metadata">Custom metadata</option>
          </select>
        </label>
        {matchField.startsWith('metadata.') && (
          <input
            aria-label="Metadata pairing field"
            value={matchField.slice(9)}
            onChange={(e) => setMatchField('metadata.' + e.target.value)}
          />
        )}
        <label>
          Matched candidates
          <select value="" onChange={(e) => setRight(e.target.value)}>
            <option value="">
              {candidates.data?.length ?? 0} candidates · choose explicitly
            </option>
            {candidates.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.sampleId} · {t.condition} · {t.model}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!right && (
        <Empty
          icon={<Columns2 size={28} />}
          title="Two trajectories. One view."
        >
          Choose a second trajectory or a fork to inspect shared history,
          intervention points, and subsequent differences.
        </Empty>
      )}
      {result.isLoading && <Loading text="Aligning trajectory events…" />}
      {result.error && <ErrorState error={result.error} />}
      {data && (
        <>
          <div className="comparison-metrics">
            <table>
              <thead>
                <tr>
                  <th>TRAJECTORY SUMMARY</th>
                  <th>Original</th>
                  <th>Comparison</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Outcome</td>
                  <td>
                    <Status status={data.left.status} />
                  </td>
                  <td>
                    <Status status={data.right.status} />
                  </td>
                </tr>
                {[
                  [
                    'Events',
                    number(data.left.eventCount),
                    number(data.right.eventCount),
                  ],
                  [
                    'Tokens',
                    number(data.left.totalTokens),
                    number(data.right.totalTokens),
                  ],
                  [
                    'Duration',
                    duration(data.left.durationMs),
                    duration(data.right.durationMs),
                  ],
                  [
                    'Scores',
                    JSON.stringify(data.left.scores),
                    JSON.stringify(data.right.scores),
                  ],
                ].map(([label, a, b]) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td>{a}</td>
                    <td>{b}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ContrastiveSignals left={left} right={right} />
          <div className="divergence-summary">
            <div>
              <span>SHARED PREFIX</span>
              <strong>
                {data.commonPrefix
                  ? `#0–${data.commonPrefix - 1}`
                  : 'No shared prefix'}
              </strong>
            </div>
            <ArrowRight size={14} />
            <div>
              <span>INTERVENTION POINT</span>
              <strong>
                {data.interventionIndex != null
                  ? `#${data.interventionIndex}`
                  : 'Independent trajectories'}
              </strong>
            </div>
            <ArrowRight size={14} />
            <div>
              <span>FIRST BEHAVIOURAL DIFFERENCE</span>
              <strong>
                {data.firstBehaviouralDivergence
                  ? `Original #${data.firstBehaviouralDivergence.left ?? '—'} · comparison #${data.firstBehaviouralDivergence.right ?? '—'}`
                  : 'None observed'}
              </strong>
            </div>
          </div>
          <div className="comparison-toolbar">
            <span>DIVERGENCE VIEW</span>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={differencesOnly}
                onChange={(e) => setDifferencesOnly(e.target.checked)}
              />
              Differences only
            </label>
            <span className="muted">{rows.length} aligned rows</span>
          </div>
          <div className="pair-column-headings">
            <span>ORIGINAL · sample_{data.left.sampleId}</span>
            <span>COMPARISON · sample_{data.right.sampleId}</span>
          </div>
          <div className="pair-scroll" ref={ref}>
            <div
              style={{
                height: virtualizer.getTotalSize(),
                position: 'relative',
              }}
            >
              {virtualizer.getVirtualItems().map((v) => {
                const row = rows[v.index]
                return (
                  <div
                    key={v.index}
                    className={`pair-row ${row.changed ? 'pair-changed' : ''} ${row.intervention ? 'pair-intervention' : ''}`}
                    style={{
                      height: v.size,
                      transform: `translateY(${v.start}px)`,
                    }}
                  >
                    {([row.left, row.right] as const).map((event, i) => (
                      <button
                        key={i}
                        onClick={() => {
                          if (event) {
                            ui.selectTrajectory(i ? right : left)
                            ui.jump(event.index)
                          }
                        }}
                      >
                        <div>
                          <span>
                            {event
                              ? `#${event.index} · ${event.toolName || event.type}`
                              : '—'}
                          </span>
                          {row.intervention && <small>intervention</small>}
                        </div>
                        <p>
                          {event?.preview ||
                            (event ? '(empty content)' : '[no matching event]')}
                        </p>
                      </button>
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
          <p className="comparison-method">
            <Info size={12} />
            {data.method}
          </p>
        </>
      )}
    </>
  )
}
function GroupView() {
  const ui = useUI()
  const experiments = useExperiments(ui.workspaceId)
  const definitions = useClassifiers()
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [conditionA, setConditionA] = useState('')
  const [conditionB, setConditionB] = useState('')
  const [drill, setDrill] = useState<{ group: number; metric: string } | null>(
    null,
  )
  const [memberPage, setMemberPage] = useState(0)
  const groups = [a, b].map((experimentId, i) => ({
    experimentId,
    filters: [conditionA, conditionB][i]
      ? [{ field: 'condition', op: 'eq', value: [conditionA, conditionB][i] }]
      : [],
  }))
  const result = useQuery({
    queryKey: ['group-comparison', ui.workspaceId, groups],
    queryFn: () =>
      rpc<Aggregate[]>('compare.groups', {
        workspaceId: ui.workspaceId,
        groups,
      }),
    enabled: !!a && !!b,
  })
  const members = useQuery({
    queryKey: ['comparison-members', drill, groups, memberPage],
    queryFn: () =>
      rpc<{
        items: { id: string; sampleId: string; status: string }[]
        total: number
      }>('compare.members', {
        workspaceId: ui.workspaceId,
        group: groups[drill!.group],
        metric: drill!.metric,
        offset: memberPage * 50,
      }),
    enabled: !!drill,
  })
  return (
    <>
      <div className="comparison-selectors">
        {[a, b].map((value, i) => (
          <label key={i}>
            <span>GROUP {i ? 'B' : 'A'}</span>
            <select
              value={value}
              onChange={(e) => {
                ;(i ? setB : setA)(e.target.value)
                setDrill(null)
              }}
            >
              <option value="">Choose experiment…</option>
              {experiments.data?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
            <input
              placeholder="Optional condition"
              value={i ? conditionB : conditionA}
              onChange={(e) =>
                (i ? setConditionB : setConditionA)(e.target.value)
              }
            />
          </label>
        ))}
      </div>
      {result.isLoading && <Loading />}
      {result.error && <ErrorState error={result.error} />}{' '}
      {result.data && (
        <div className="group-table">
          <table>
            <thead>
              <tr>
                <th>METRIC · CLICK TO INSPECT MEMBERS</th>
                <th>A</th>
                <th>B</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['trajectories', 'Trajectories'],
                ['success', 'Known successful outcomes'],
                ['successRate', 'Success rate among known outcomes'],
                ['errors', 'Execution errors'],
                ['meanTokens', 'Mean tokens'],
                ['scoredOutcomes', 'Trajectories with known outcomes'],
              ].map(([key, label]) => (
                <tr key={key}>
                  <td>{label}</td>
                  {result.data!.map((g, i) => (
                    <td key={i}>
                      <button
                        onClick={() => {
                          setDrill({ group: i, metric: key })
                          setMemberPage(0)
                        }}
                      >
                        {key === 'successRate'
                          ? g.successRate == null
                            ? '—'
                            : `${(g.successRate * 100).toFixed(1)}%`
                          : number(g[key as keyof Aggregate] as number)}
                        <ArrowDown size={11} />
                      </button>
                    </td>
                  ))}
                </tr>
              ))}
              {[
                ...new Set(
                  result.data.flatMap((g) =>
                    g.classifiers.map((c) => c.classifierId),
                  ),
                ),
              ].map((id) => (
                <tr key={id}>
                  <td>
                    {definitions.data?.find((c) => c.id === id)?.name || id}
                    <small>Mean of per-trajectory means · above 0.8 · n</small>
                  </td>
                  {result.data!.map((g, i) => {
                    const c = g.classifiers.find((c) => c.classifierId === id)
                    return (
                      <td key={i}>
                        <button
                          onClick={() => {
                            setDrill({ group: i, metric: id })
                            setMemberPage(0)
                          }}
                        >
                          {c
                            ? `${c.meanScore.toFixed(2)} · ${(c.aboveThreshold * 100).toFixed(0)}% · ${c.n}`
                            : '—'}
                          <ArrowDown size={11} />
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            Unknown outcomes are kept separate. Classifier means weight
            trajectories equally; coverage is shown as n.
          </p>
        </div>
      )}
      {drill && (
        <div className="metric-drill">
          <div className="detail-heading">
            GROUP {drill.group ? 'B' : 'A'} · {drill.metric}
            <Button size="sm" variant="ghost" onClick={() => setDrill(null)}>
              Close
            </Button>
          </div>
          <p className="muted small">
            {members.data?.total} trajectories in the contributing group. Open a
            trajectory to inspect events and classifier coverage.
          </p>
          {members.data?.items.map((t) => (
            <button
              className="text-row"
              key={t.id}
              onClick={() => ui.selectTrajectory(t.id)}
            >
              sample_{t.sampleId}
              <Status status={t.status} />
              <ArrowRight size={13} />
            </button>
          ))}
          <div className="pagination">
            <span>Page {memberPage + 1}</span>
            <Button
              variant="ghost"
              size="sm"
              disabled={!memberPage}
              onClick={() => setMemberPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={(memberPage + 1) * 50 >= (members.data?.total || 0)}
              onClick={() => setMemberPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
      {!a || !b ? (
        <Empty title="Compare two experimental groups">
          Choose experiments and optionally restrict each to a condition.
        </Empty>
      ) : null}
    </>
  )
}
