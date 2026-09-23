import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
import { rpc } from '@/lib/api'
import { useUI } from '@/stores/ui'
import { Status } from '@/components/common/Primitives'
import type { Page, Trajectory } from '@/types/domain'

/** Search and page in DuckDB; never mount 10,000 select options. */
export function TrajectoryPicker({
  value,
  onChange,
  exclude,
  placeholder = 'Select trajectory…',
}: {
  value: string
  onChange: (id: string) => void
  exclude?: string
  placeholder?: string
}) {
  const workspaceId = useUI((s) => s.workspaceId)
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const ref = useRef<HTMLDivElement>(null)
  const selected = useQuery({
    queryKey: ['trajectory-summary', value],
    queryFn: () => rpc<Trajectory>('trajectories.summary', { id: value }),
    enabled: !!value,
  })
  const result = useQuery({
    queryKey: ['trajectory-picker', workspaceId, search, page],
    queryFn: () =>
      rpc<Page<Trajectory>>('trajectories.list', {
        workspaceId,
        filters: search
          ? [{ field: 'sample', op: 'contains', value: search }]
          : [],
        limit: 30,
        offset: page * 30,
      }),
    enabled: open,
  })
  useEffect(() => {
    const outside = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [open])
  return (
    <div
      className="trajectory-picker"
      ref={ref}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          setOpen(false)
          e.stopPropagation()
        }
      }}
    >
      <button
        className="trajectory-picker-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span>
          {selected.data
            ? `sample_${selected.data.sampleId} · ${selected.data.condition || 'unassigned'}`
            : value
              ? 'Loading selection…'
              : placeholder}
        </span>
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="trajectory-picker-popover">
          <div className="search-input">
            <Search size={13} />
            <input
              autoFocus
              aria-label="Search sample IDs"
              placeholder="Search all sample IDs…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(0)
              }}
            />
          </div>
          <div
            className="trajectory-picker-options"
            role="listbox"
            aria-label="Trajectories"
          >
            {result.isLoading && <p className="muted small">Loading…</p>}
            {result.error && (
              <p className="inline-error">{result.error.message}</p>
            )}
            {result.data?.items
              .filter((t) => t.id !== exclude)
              .map((t) => (
                <button
                  role="option"
                  aria-selected={t.id === value}
                  key={t.id}
                  onClick={() => {
                    onChange(t.id)
                    setOpen(false)
                  }}
                >
                  <span>
                    sample_{t.sampleId}
                    <small>
                      {t.condition || 'unassigned'} ·{' '}
                      {t.parentTrajectoryId ? 'branch' : 'original'}
                    </small>
                  </span>
                  <Status status={t.status} small />
                </button>
              ))}
          </div>
          <footer>
            <span>{result.data?.total || 0} matches</span>
            <button
              aria-label="Previous trajectories"
              disabled={!page}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft size={13} />
            </button>
            <button
              aria-label="Next trajectories"
              disabled={(page + 1) * 30 >= (result.data?.total || 0)}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight size={13} />
            </button>
          </footer>
        </div>
      )}
    </div>
  )
}

export function TrajectorySelection({
  value,
  onChange,
}: {
  value: string[]
  onChange: (ids: string[]) => void
}) {
  return (
    <div className="trajectory-selection">
      <TrajectoryPicker
        value=""
        placeholder="Add a trajectory from any indexed sample…"
        onChange={(id) => {
          if (!value.includes(id)) onChange([...value, id])
        }}
      />
      <div className="selected-trajectories">
        {value.map((id) => (
          <SelectedTrajectory
            key={id}
            id={id}
            onRemove={() => onChange(value.filter((x) => x !== id))}
          />
        ))}
      </div>
      <span className="muted small">{value.length} trajectories selected</span>
    </div>
  )
}
function SelectedTrajectory({
  id,
  onRemove,
}: {
  id: string
  onRemove: () => void
}) {
  const query = useQuery({
    queryKey: ['trajectory-summary', id],
    queryFn: () => rpc<Trajectory>('trajectories.summary', { id }),
  })
  return (
    <span className="selected-trajectory-chip">
      {query.data ? `sample_${query.data.sampleId}` : 'Loading…'}
      <button aria-label="Remove selected trajectory" onClick={onRemove}>
        <X size={11} />
      </button>
    </span>
  )
}
