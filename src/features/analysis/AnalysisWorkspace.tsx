import { DetectorEditor } from './DetectorEditor'
import { ArtifactImport } from './ArtifactImport'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Flag, GitBranch } from 'lucide-react'
import { useState } from 'react'
import { ClassifierWorkspace } from '@/features/classifiers/ClassifierWorkspace'
import { Button } from '@/components/ui/button'
import { Empty } from '@/components/common/Primitives'
import { TrajectoryPicker } from '@/components/trajectory/TrajectoryPicker'
import { useTimeline, useTrajectories } from '@/hooks/queries'
import { rpc } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useUI, type AnalysisTab } from '@/stores/ui'
import type { Trajectory } from '@/types/domain'
import { useOverview, useSignals } from './queries'
import { ExecutionGraph } from './ExecutionGraph'
import { AnalysisOverview, SignalList } from './AnalysisOverview'
import { ContrastiveSignals } from './ContrastiveSignals'
import { channelHelp } from './channels'

type Group = 'overview' | 'signals' | 'compare' | 'internals' | 'notes'
export const analysisNavigation: {
  id: Group
  label: string
  sub?: [AnalysisTab, string][]
}[] = [
  { id: 'overview', label: 'Overview' },
  {
    id: 'signals',
    label: 'Signals',
    sub: [
      ['signals/semantic', 'Semantic / LLM'],
      ['signals/rules', 'Rules'],
      ['signals/statistical', 'Statistical'],
      ['signals/environment', 'Environment'],
    ],
  },
  { id: 'compare', label: 'Compare' },
  {
    id: 'internals',
    label: 'Internals',
    sub: [
      ['internals/graph', 'Multi-agent / graph'],
      ['internals/imported', 'Imported internal signals'],
    ],
  },
  { id: 'notes', label: 'Notes' },
]
const groupOf = (tab: AnalysisTab) => tab.split('/')[0] as Group

export function AnalysisWorkspace() {
  const ui = useUI()
  const tab = ui.analysisTab
  const active = analysisNavigation.find((g) => g.id === groupOf(tab))!
  return (
    <div className="analysis-workspace">
      <nav className="analysis-tabs" aria-label="Analysis sections">
        {analysisNavigation.map((g) => (
          <button
            key={g.id}
            aria-current={g.id === active.id ? 'page' : undefined}
            className={g.id === active.id ? 'active' : ''}
            onClick={() =>
              ui.set({ analysisTab: g.sub ? g.sub[0][0] : (g.id as AnalysisTab) })
            }
          >
            {g.label}
          </button>
        ))}
      </nav>
      {active.sub && (
        <nav
          className="analysis-subtabs"
          aria-label={`${active.label} sections`}
        >
          {active.sub.map(([id, label]) => (
            <button
              key={id}
              aria-current={id === tab ? 'page' : undefined}
              className={cn(id === tab && 'active')}
              onClick={() => ui.set({ analysisTab: id })}
            >
              {label}
            </button>
          ))}
        </nav>
      )}
      {tab === 'overview' ? (
        <AnalysisOverview />
      ) : tab === 'signals/semantic' ? (
        <ClassifierWorkspace />
      ) : tab === 'signals/rules' || tab === 'signals/statistical' ? (
        <DetectorEditor
          key={tab}
          kind={tab === 'signals/rules' ? 'rule' : 'statistical'}
        />
      ) : tab === 'signals/environment' ? (
        <ChannelSignals channel="GRAY_BOX" title="Environment observations" />
      ) : tab === 'compare' ? (
        <CompareRun />
      ) : tab === 'internals/graph' ? (
        <GraphPanel />
      ) : tab === 'internals/imported' ? (
        <div className="feature-page">
          <h2>Imported internal signals</h2>
          <p className="muted">
            External artifact references and imported probe, logit or SAE
            measurements. No model instrumentation is installed.
          </p>
          <ArtifactImport />
          <ChannelSignals channel="WHITE_BOX" embedded />
        </div>
      ) : (
        <NotesPanel />
      )}
    </div>
  )
}

function ChannelSignals({
  channel,
  title,
  embedded = false,
}: {
  channel: 'GRAY_BOX' | 'WHITE_BOX'
  title?: string
  embedded?: boolean
}) {
  const ui = useUI()
  const signals = useSignals(ui.trajectoryId)
  const rows = (signals.data ?? []).filter((s) => s.channel === channel)
  const body = (
    <>
      {title && <h2>{title}</h2>}
      {!embedded && <p className="muted">{channelHelp[channel]}</p>}
      <SignalList rows={rows} />
      {signals.error && <p className="inline-error">{signals.error.message}</p>}
    </>
  )
  return embedded ? body : <div className="feature-page">{body}</div>
}

function GraphPanel() {
  const ui = useUI()
  const overview = useOverview(ui.trajectoryId)
  return (
    <div className="feature-page">
      <h2>Multi-agent / graph</h2>
      <p className="muted">
        Recorded parents, message envelopes and shared artifacts. A parent does
        not prove communication.
      </p>
      {overview.data ? (
        overview.data.relationships.length ||
        overview.data.coordinates.points.some((p) => p.agent) ? (
          <ExecutionGraph overview={overview.data} />
        ) : (
          <p className="muted">
            This run records no agent identities or relationships, so there is
            no graph to show.
          </p>
        )
      ) : (
        <p className="muted">Deriving recorded relationships…</p>
      )}
    </div>
  )
}

/** Candidates are suggestions only: the researcher chooses the pair explicitly. */
function CompareRun() {
  const ui = useUI()
  const [right, setRight] = useState(ui.comparisonRight ?? '')
  const trajectories = useTrajectories(ui.workspaceId)
  const matches = useQuery({
    queryKey: ['matched-trajectories', ui.trajectoryId, 'sampleId'],
    queryFn: () =>
      rpc<Trajectory[]>('analysis.matchCandidates', {
        controlId: ui.trajectoryId,
        field: 'sampleId',
      }),
    enabled: !!ui.trajectoryId,
  })
  const branches =
    trajectories.data?.items.filter(
      (t) => t.parentTrajectoryId === ui.trajectoryId,
    ) ?? []
  const suggestions = [
    ...branches.map((t) => ({ t, why: 'Fork branch of this run' })),
    ...(matches.data ?? [])
      .filter((t) => !t.parentTrajectoryId)
      .map((t) => ({ t, why: `Same sample · ${t.condition || 'other condition'}` })),
  ]
  if (!ui.trajectoryId)
    return <Empty title="Select a trajectory to compare" />
  return (
    <div className="feature-page">
      <h2>Compare this run</h2>
      <p className="muted">
        Observed differences between this run and one other trajectory. These
        comparisons are descriptive, not causal claims.
      </p>
      {suggestions.length > 0 && (
        <div className="suggested-pairs" role="group" aria-label="Suggested comparisons">
          {suggestions.slice(0, 4).map(({ t, why }) => (
            <button
              key={t.id}
              className={cn('suggested-pair', right === t.id && 'active')}
              aria-pressed={right === t.id}
              onClick={() => setRight(t.id)}
            >
              {t.parentTrajectoryId ? <GitBranch size={13} /> : null}
              <strong>sample_{t.sampleId}</strong>
              <small>{why}</small>
            </button>
          ))}
        </div>
      )}
      <label className="compare-run-picker">
        <span>Compare with</span>
        <TrajectoryPicker
          value={right}
          onChange={setRight}
          exclude={ui.trajectoryId}
          placeholder="Select trajectory or branch…"
        />
      </label>
      {right ? (
        <>
          <ContrastiveSignals left={ui.trajectoryId} right={right} />
          <Button
            variant="outline"
            onClick={() => ui.set({ comparisonRight: right, section: 'compare' })}
          >
            Open aligned event comparison
            <ArrowRight size={13} />
          </Button>
        </>
      ) : (
        <p className="muted">Choose a suggested pair or any trajectory.</p>
      )}
    </div>
  )
}

function NotesPanel() {
  const ui = useUI()
  const timeline = useTimeline(ui.trajectoryId)
  const notes = timeline.data?.annotations ?? []
  return (
    <div className="feature-page">
      <div className="feature-heading compact">
        <div>
          <h2>Notes</h2>
          <p className="muted">
            Human annotations stay linked to exact event ranges.
          </p>
        </div>
        <Button
          variant="outline"
          disabled={!ui.trajectoryId}
          onClick={() => ui.set({ modal: 'annotate' })}
        >
          <Flag size={13} />
          Annotate event #{ui.selectedIndex}
        </Button>
      </div>
      {notes.length === 0 ? (
        <p className="muted">No annotations on this run yet.</p>
      ) : (
        <ul className="notes-list">
          {notes.map((a) => (
            <li key={a.id}>
              <button onClick={() => ui.focus(a.startEventIndex, a.endEventIndex, a.label)}>
                <span className="moment-index">
                  #{a.startEventIndex}
                  {a.endEventIndex !== a.startEventIndex && `–${a.endEventIndex}`}
                </span>
                <span>
                  <strong>{a.label}</strong>
                  <small>{a.note || 'No note'}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
