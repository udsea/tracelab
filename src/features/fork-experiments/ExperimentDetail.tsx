import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Status } from '@/components/common/Primitives'
import { rpc } from '@/lib/api'
import { useUI } from '@/stores/ui'
import type {
  ExperimentDetail as Detail,
  ExperimentStart,
  ForkTrial,
} from '@/types/fork-experiments'

export function ExperimentDetail({ id }: { id: string }) {
  const ui = useUI()
  const client = useQueryClient()
  const [cell, setCell] = useState<{ caseId: string; armId: string }>()
  const [offset, setOffset] = useState(0)
  const detail = useQuery({
    queryKey: ['fork-experiment', id],
    queryFn: () => rpc<Detail>('forkExperiments.get', { id }),
    refetchInterval: 2000,
  })
  const trials = useQuery({
    queryKey: ['fork-trials', id, cell, offset],
    queryFn: () =>
      rpc<ForkTrial[]>('forkExperiments.trials', {
        experimentId: id,
        ...cell,
        offset,
        limit: 50,
      }),
    refetchInterval: 2000,
  })
  const action = useMutation({
    mutationFn: async (kind: 'cancel' | 'resume') => {
      if (kind === 'cancel')
        return rpc('jobs.cancel', { id: detail.data?.experiment.jobId })
      const result = await rpc<ExperimentStart>('forkExperiments.resume', {
        id,
      })
      if (!result.started)
        throw Error(
          result.preview?.cells
            .filter((c) => !c.supported)
            .map((c) => `${c.caseId}/${c.armId}: ${c.reason}`)
            .join('; ') || 'Resume preflight failed',
        )
      return result
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['fork-experiment', id] })
    },
  })
  if (detail.error)
    return <p className="inline-error">{String(detail.error)}</p>
  if (!detail.data) return <p>Loading experiment…</p>
  const { experiment: exp, progress, cells, usage } = detail.data
  return (
    <div>
      <h2>{exp.name}</h2>
      <Status status={exp.status} />
      <p>
        {progress.finalized} / {progress.total} finalized · {progress.complete}{' '}
        complete · {progress.error} error · {progress.interrupted} interrupted ·{' '}
        {progress.cancelled} cancelled · {progress.pending} pending
      </p>
      <p>
        Reported model calls: {usage.modelSteps} ({usage.modelCallReports} child
        reports) · generated tool calls: {usage.toolCalls} · replayed:{' '}
        {usage.replayedToolCalls} · stubbed: {usage.stubbedToolCalls} · reported
        tokens: {usage.reportedTotalTokens} ({usage.tokenReports} child
        reports). Branches remain unscored.
      </p>
      {exp.status === 'running' && (
        <Button
          disabled={action.isPending}
          onClick={() => action.mutate('cancel')}
        >
          Cancel experiment
        </Button>
      )}
      {['partial', 'cancelled'].includes(exp.status) &&
        progress.pending > 0 && (
          <Button
            disabled={action.isPending}
            onClick={() => action.mutate('resume')}
          >
            Resume pending trials
          </Button>
        )}
      {action.error && <p className="inline-error">{String(action.error)}</p>}
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" aria-label="Experiment trial matrix">
          <thead>
            <tr>
              <th>Source case</th>
              {exp.arms.map((a) => (
                <th key={a.id}>
                  {a.name} · {a.role}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {exp.cases.map((c) => (
              <tr key={c.id}>
                <th>
                  {c.label || c.id}
                  <small style={{ display: 'block' }}>{c.sourceEventId}</small>
                </th>
                {exp.arms.map((a) => {
                  const summary = cells.find(
                    (s) => s.caseId === c.id && s.armId === a.id,
                  )
                  return (
                    <td key={a.id}>
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setCell({ caseId: c.id, armId: a.id })
                          setOffset(0)
                        }}
                      >
                        {summary?.progress.complete}/{summary?.progress.total}{' '}
                        complete · {summary?.progress.error || 0} errors
                      </Button>
                      <small style={{ display: 'block' }}>
                        {Object.entries(summary?.terminationCounts || {})
                          .map(([reason, n]) => `${reason}: ${n}`)
                          .join(' · ')}
                      </small>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>{cell ? `${cell.caseId} / ${cell.armId}` : 'All trials'}</h3>
      {cell && (
        <Button
          variant="ghost"
          onClick={() => {
            setCell(undefined)
            setOffset(0)
          }}
        >
          Show all arms and pairs
        </Button>
      )}
      {trials.error && <p className="inline-error">{String(trials.error)}</p>}
      <p>
        Pair = source case / replication. Seeds are paired requests, not
        guarantees of identical randomness.
      </p>
      {trials.data?.map((t) => (
        <div className="fork-tree-child" key={t.id}>
          <Button
            variant="ghost"
            disabled={!t.childTrajectoryId}
            onClick={() =>
              t.childTrajectoryId && ui.selectTrajectory(t.childTrajectoryId)
            }
          >
            {t.caseId} / {t.armId} · replicate {t.replicationIndex + 1}
          </Button>
          <Status status={t.status} />
          <span>
            Pair {t.pairKey} · requested seed {t.requestedSeed ?? 'none'} ·
            schedule #{t.scheduleOrdinal}
          </span>
          <span>{t.metadata.terminationReason}</span>
          {t.error && <span className="inline-error">{t.error}</span>}
        </div>
      ))}
      <Button
        variant="outline"
        disabled={offset === 0}
        onClick={() => setOffset(Math.max(0, offset - 50))}
      >
        Previous trials
      </Button>
      <Button
        variant="outline"
        disabled={(trials.data?.length ?? 0) < 50}
        onClick={() => setOffset(offset + 50)}
      >
        Next trials
      </Button>
      <details>
        <summary>Concrete specification and provenance</summary>
        <pre>{JSON.stringify(exp, null, 2)}</pre>
      </details>
    </div>
  )
}
