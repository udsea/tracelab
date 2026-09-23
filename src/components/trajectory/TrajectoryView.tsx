import {
  AlignLeft,
  ArrowUpRight,
  ChevronRight,
  Columns2,
  GitBranch,
  List,
  Maximize2,
  X,
} from 'lucide-react'
import { useTrajectory } from '@/hooks/queries'
import { useUI, notify } from '@/stores/ui'
import { Button } from '@/components/ui/button'
import {
  Empty,
  ErrorState,
  Loading,
  Status,
} from '@/components/common/Primitives'
import { duration, number, shortModel } from '@/lib/utils'
import { openNative, rpc } from '@/lib/api'
import { EventList } from './EventList'
import { SourceBadge } from '@/features/sources/SourcePanel'
export function TrajectoryView() {
  const ui = useUI()
  const query = useTrajectory(ui.trajectoryId)
  if (!ui.trajectoryId)
    return (
      <Empty title="Choose a trajectory">
        Add trajectory source to begin exploring agent behaviour.
      </Empty>
    )
  if (query.isLoading) return <Loading />
  if (query.error)
    return (
      <ErrorState
        error={query.error}
        retry={() => {
          void query.refetch()
        }}
      />
    )
  const t = query.data!.trajectory
  return (
    <section className="trajectory-panel">
      <div className="trajectory-heading">
        <div className="breadcrumbs">
          <span>{t.task?.replace(' · baseline', '') || 'Experiment'}</span>
          <ChevronRight size={12} />
          <span>sample_{t.sampleId}</span>
        </div>
        <div className="trajectory-title">
          <h1>
            Trajectory <span>#{t.sampleId.padStart(3, '0')}</span>
          </h1>
          <Status status={t.status} />
          <SourceBadge trajectory={t} />
          <div className="heading-spacer" />
          <Button
            variant="ghost"
            size="icon"
            title={
              t.sourceRef?.kind && t.sourceRef.kind !== 'local'
                ? 'Native Inspect view is available for local logs'
                : 'Open in Inspect'
            }
            disabled={
              (!!t.metadata.importFormat &&
                t.metadata.importFormat !== 'inspect') ||
              (!!t.sourceRef && t.sourceRef.kind !== 'local')
            }
            onClick={() => {
              void rpc<{ url: string; note: string }>('inspect.open', {
                experimentId: t.experimentId,
                sampleId: t.sampleId,
              })
                .then(async (r) => {
                  notify(r.note)
                  await openNative(r.url)
                })
                .catch((e) => notify(String(e)))
            }}
          >
            <ArrowUpRight size={16} />
          </Button>
          {t.parentTrajectoryId && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                ui.set({
                  comparisonRight: t.id,
                  trajectoryId: t.parentTrajectoryId,
                  section: 'compare',
                })
              }}
            >
              <Columns2 size={13} />
              Compare to parent
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={!query.data?.capabilities.contextOnly}
            title={query.data?.capabilities.reason}
            onClick={() => ui.set({ modal: 'fork' })}
          >
            <GitBranch size={13} />
            Fork
          </Button>
        </div>
        <div className="trajectory-meta">
          <span className="model-dot" />
          <span>{shortModel(t.model)}</span>
          <i />
          <span>{number(t.eventCount)} events</span>
          <i />
          <span>{number(t.totalTokens)} tokens</span>
          <i />
          <span>{duration(t.durationMs)}</span>
        </div>
      </div>
      <div className="event-toolbar">
        <div className="segmented-control">
          {[
            ['all', 'All events'],
            ['tools', 'Tools'],
            ['reasoning', 'Reasoning'],
            ['errors', 'Errors'],
          ].map(([value, label]) => (
            <button
              key={value}
              className={ui.mode === value ? 'active' : ''}
              onClick={() => ui.set({ mode: value })}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <button
            title={ui.expanded ? 'Compact mode' : 'Expanded mode'}
            className="icon-button"
            onClick={() => ui.set({ expanded: !ui.expanded })}
          >
            {ui.expanded ? <List size={15} /> : <AlignLeft size={15} />}
          </button>
          <span className="toolbar-divider" />
          <button
            title="Jump to last event"
            className="icon-button"
            onClick={() => ui.jump(Math.max(0, t.eventCount - 1))}
          >
            <Maximize2 size={14} />
          </button>
        </div>
      </div>
      {ui.range && (
        <div className="range-banner">
          {ui.range.label}
          <span>
            #{ui.range.start}–{ui.range.end}
          </span>
          <button
            className="icon-button"
            title="Show all events"
            onClick={() => ui.set({ range: null })}
          >
            <X size={12} />
          </button>
        </div>
      )}
      <EventList />
      <div className="trajectory-bottom">
        <span>
          <span className="green-dot" />
          Original log preserved
        </span>
        <span>
          Event #{ui.selectedIndex}{' '}
          <span className="muted">of {t.eventCount - 1}</span>
        </span>
      </div>
    </section>
  )
}
