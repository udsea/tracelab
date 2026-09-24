import { DetectorEditor } from './DetectorEditor'
import { ArtifactImport } from './ArtifactImport'
import { useState } from 'react'
import { ClassifierWorkspace } from '@/features/classifiers/ClassifierWorkspace'
import { ComparisonWorkspace } from '@/features/comparisons/ComparisonWorkspace'
import { useUI } from '@/stores/ui'
import type { AnalysisSignal } from '@/types/analysis'
import { useOverview, useSignals } from './queries'
import { ExecutionGraph } from './ExecutionGraph'
const tabs = [
  'Summary',
  'LLM Detectors',
  'Rules',
  'Statistical',
  'Contrastive',
  'Environment',
  'Multi-agent / Graph',
  'Internal Signals',
  'Human Annotations',
]
export function AnalysisWorkspace() {
  const [tab, setTab] = useState('Summary'),
    ui = useUI(),
    overview = useOverview(ui.trajectoryId),
    signals = useSignals(ui.trajectoryId)
  const rows = (signals.data ?? []).filter((s) =>
    tab === 'Environment'
      ? s.channel === 'GRAY_BOX'
      : tab === 'Internal Signals'
        ? s.channel === 'WHITE_BOX'
        : tab === 'Human Annotations'
          ? s.sourceType === 'human'
          : true,
  )
  return (
    <div className="analysis-workspace">
      <nav className="analysis-tabs">
        {tabs.map((t) => (
          <button
            key={t}
            className={tab === t ? 'active' : ''}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </nav>
      {tab === 'LLM Detectors' ? (
        <ClassifierWorkspace />
      ) : tab === 'Rules' || tab === 'Statistical' ? (
        <DetectorEditor kind={tab === 'Rules' ? 'rule' : 'statistical'} />
      ) : tab === 'Contrastive' ? (
        <ComparisonWorkspace />
      ) : (
        <div className="feature-page">
          <h2>{tab === 'Summary' ? 'Run analysis' : tab}</h2>
          <p className="muted">
            Research heuristics · not validated ground truth. Evidence channels
            remain separate.
          </p>
          {tab === 'Summary' && (
            <>
              <p>
                {overview.data?.outline.filter((n) => n.kind === 'segment')
                  .length ?? 0}{' '}
                narrative segments ·{' '}
                {overview.data?.outline.filter((n) => n.kind === 'moment')
                  .length ?? 0}{' '}
                important moments
              </p>
              <h3>Evaluation Awareness suite</h3>
              <p>
                Inspect semantic judgment, evaluator access, language mentions,
                change points, contrastive shifts and human annotations
                separately.
              </p>
              <button onClick={() => setTab('LLM Detectors')}>
                Configure semantic detector
              </button>
              <button onClick={() => setTab('Rules')}>
                Configure observable rules
              </button>
              <button onClick={() => setTab('Statistical')}>
                Measure behavioral shifts
              </button>
            </>
          )}
          {tab === 'Multi-agent / Graph' && overview.data && (
            <ExecutionGraph overview={overview.data} />
          )}
          {tab === 'Internal Signals' && <ArtifactImport />}
          {tab === 'Internal Signals' && (
            <p>
              External artifact references and imported probe/logit/SAE
              measurements appear here. No model instrumentation is installed.
            </p>
          )}
          {tab === 'Human Annotations' && (
            <button onClick={() => ui.set({ modal: 'annotate' })}>
              Annotate selected event / range
            </button>
          )}
          <SignalList rows={rows} />
          {signals.error && (
            <p className="inline-error">{signals.error.message}</p>
          )}
        </div>
      )}
    </div>
  )
}
function SignalList({ rows }: { rows: AnalysisSignal[] }) {
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
              {s.sourceType} · #{s.startEventIndex}–{s.endEventIndex}
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
      {!rows.length && (
        <p>
          No measurements yet. Run a detector or import associated measurements.
        </p>
      )}
    </div>
  )
}
