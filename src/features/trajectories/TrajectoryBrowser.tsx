import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, ListFilter, Plus, X } from 'lucide-react'
import { useClassifiers, useExperiments } from '@/hooks/queries'
import { Button } from '@/components/ui/button'
import { ErrorState, Loading, Status } from '@/components/common/Primitives'
import { rpc } from '@/lib/api'
import { duration, number, shortModel } from '@/lib/utils'
import { useUI } from '@/stores/ui'
import type { Filter, Page, Trajectory } from '@/types/domain'
export function TrajectoryBrowser() {
  const ui = useUI()
  const experiments = useExperiments(ui.workspaceId)
  const classifiers = useClassifiers()
  const [experimentId, setExperimentId] = useState('')
  const [filters, setFilters] = useState<Filter[]>([])
  const [page, setPage] = useState(0)
  const query = useQuery({
    queryKey: ['browse', ui.workspaceId, experimentId, filters, page],
    queryFn: () =>
      rpc<Page<Trajectory>>('trajectories.list', {
        workspaceId: ui.workspaceId,
        experimentId: experimentId || undefined,
        filters,
        offset: page * 50,
        limit: 50,
      }),
  })
  function change(index: number, patch: Partial<Filter>) {
    setPage(0)
    setFilters((old) =>
      old.map((f, i) => (i === index ? { ...f, ...patch } : f)),
    )
  }
  return (
    <div className="feature-page">
      <div className="feature-heading">
        <div>
          <span className="eyebrow">WORKSPACE EXPLORER</span>
          <h1>Trajectories</h1>
          <p>Find the runs that answer your research question.</p>
        </div>
        <span className="count-badge">
          {number(query.data?.total)} trajectories
        </span>
      </div>
      <div className="filter-panel">
        <div className="filter-heading">
          <ListFilter size={15} />
          <select
            value={experimentId}
            onChange={(e) => {
              setExperimentId(e.target.value)
              setPage(0)
            }}
          >
            <option value="">All experiments</option>
            {experiments.data?.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setFilters((f) => [
                ...f,
                { field: 'status', op: 'eq', value: 'success' },
              ])
              setPage(0)
            }}
          >
            <Plus size={12} />
            Add filter
          </Button>
          <span>All filters must match</span>
        </div>
        {filters.map((filter, index) => (
          <div className="filter-row" key={index}>
            <span>{index ? 'AND' : 'WHERE'}</span>
            <select
              value={filter.field}
              onChange={(e) =>
                change(index, {
                  field: e.target.value,
                  value: ['tokens', 'duration', 'score', 'classifier'].includes(
                    e.target.value,
                  )
                    ? 0
                    : '',
                })
              }
            >
              {[
                ['status', 'Status'],
                ['condition', 'Condition'],
                ['model', 'Model'],
                ['score', 'Score'],
                ['tokens', 'Token count'],
                ['duration', 'Duration (ms)'],
                ['error', 'Has error'],
                ['annotation', 'Annotation label'],
                ['classifier', 'Classifier score'],
                ['classifierLabel', 'Classifier label'],
                ['forkStatus', 'Fork status'],
                ['parent', 'Parent trajectory'],
              ].map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            {filter.field.startsWith('classifier') && (
              <select
                value={filter.key || ''}
                onChange={(e) => change(index, { key: e.target.value })}
              >
                <option value="">Select classifier…</option>
                {classifiers.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
            {filter.field === 'score' && (
              <input
                placeholder="Scorer name"
                value={filter.key || ''}
                onChange={(e) => change(index, { key: e.target.value })}
              />
            )}
            <select
              value={filter.op}
              onChange={(e) => change(index, { op: e.target.value })}
            >
              {[
                ['eq', '='],
                ['gt', '>'],
                ['gte', '≥'],
                ['lt', '<'],
                ['lte', '≤'],
              ].map(([op, label]) => (
                <option key={op} value={op}>
                  {label}
                </option>
              ))}
            </select>
            {filter.field === 'status' ? (
              <select
                value={filter.value}
                onChange={(e) => change(index, { value: e.target.value })}
              >
                {[
                  'success',
                  'failure',
                  'unknown',
                  'error',
                  'running',
                  'cancelled',
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            ) : (
              <input
                value={filter.value}
                placeholder="Value"
                disabled={filter.field === 'error'}
                onChange={(e) => change(index, { value: e.target.value })}
              />
            )}
            <Button
              size="icon"
              variant="ghost"
              title="Remove filter"
              onClick={() => {
                setFilters((f) => f.filter((_, i) => i !== index))
                setPage(0)
              }}
            >
              <X size={13} />
            </Button>
          </div>
        ))}
      </div>
      {query.isLoading && <Loading />}
      {query.error && <ErrorState error={query.error} />}
      <table className="trajectory-table">
        <thead>
          <tr>
            <th>SAMPLE</th>
            <th>CONDITION</th>
            <th>MODEL</th>
            <th>OUTCOME</th>
            <th>EVENTS</th>
            <th>TOKENS</th>
            <th>DURATION</th>
          </tr>
        </thead>
        <tbody>
          {query.data?.items.map((t) => (
            <tr key={t.id} onClick={() => ui.selectTrajectory(t.id)}>
              <td>
                <button>
                  sample_{t.sampleId}
                  <ArrowRight size={12} />
                </button>
              </td>
              <td>{t.condition || '—'}</td>
              <td>{shortModel(t.model)}</td>
              <td>
                <Status status={t.status} />
              </td>
              <td>{t.loaded ? number(t.eventCount) : 'On demand'}</td>
              <td>{number(t.totalTokens)}</td>
              <td>{duration(t.durationMs)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {query.data?.total === 0 && (
        <p className="muted table-empty">
          No trajectories match these filters.
        </p>
      )}
      <div className="pagination">
        <span>
          {query.data?.total || 0} matches · page {page + 1}
        </span>
        <Button
          variant="ghost"
          size="sm"
          disabled={!page}
          onClick={() => setPage((p) => p - 1)}
        >
          <ArrowLeft size={12} />
          Previous
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={!query.data || (page + 1) * 50 >= query.data.total}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
          <ArrowRight size={12} />
        </Button>
      </div>
    </div>
  )
}
