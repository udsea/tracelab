import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Status } from '@/components/common/Primitives'
import { rpc } from '@/lib/api'
import type { ExperimentSummary } from '@/types/fork-experiments'
import { ExperimentBuilder } from './ExperimentBuilder'
import { ExperimentDetail } from './ExperimentDetail'

export function ExperimentWorkspace({ workspaceId }: { workspaceId: string }) {
  const client = useQueryClient()
  const [selected, setSelected] = useState<string>()
  const [building, setBuilding] = useState(false)
  const [offset, setOffset] = useState(0)
  const list = useQuery({
    queryKey: ['fork-experiments', workspaceId, offset],
    queryFn: () =>
      rpc<ExperimentSummary[]>('forkExperiments.list', {
        workspaceId,
        offset,
        limit: 50,
      }),
    refetchInterval: 2500,
  })
  return (
    <div>
      <p>
        Cases × arms × replications. Concrete source-specific interventions;
        serial execution. No task-success or treatment-effect estimates.
      </p>
      <Button
        onClick={() => {
          setBuilding(!building)
          setSelected(undefined)
        }}
      >
        {building ? 'Close builder' : 'New experiment'}
      </Button>
      {building && (
        <ExperimentBuilder
          workspaceId={workspaceId}
          onStarted={(id) => {
            setSelected(id)
            setBuilding(false)
            void client.invalidateQueries({ queryKey: ['fork-experiments'] })
          }}
        />
      )}
      {!building && (
        <>
          <div className="fork-tree">
            {list.data?.map((e) => (
              <button
                className="fork-tree-parent"
                key={e.id}
                onClick={() => setSelected(e.id)}
              >
                <strong>{e.name}</strong>
                <Status status={e.status} />
                <span>
                  {e.caseCount} cases × {e.armCount} arms × {e.replicationCount}{' '}
                  reps · {e.progress.finalized}/{e.progress.total} ·{' '}
                  {e.progress.error} errors ·{' '}
                  {new Date(e.createdAt).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
          {list.error && <p className="inline-error">{String(list.error)}</p>}
          <Button
            variant="ghost"
            disabled={!offset}
            onClick={() => setOffset(offset - 50)}
          >
            Previous experiments
          </Button>
          <Button
            variant="ghost"
            disabled={(list.data?.length ?? 0) < 50}
            onClick={() => setOffset(offset + 50)}
          >
            Next experiments
          </Button>
          {selected && <ExperimentDetail key={selected} id={selected} />}
        </>
      )}
    </div>
  )
}
