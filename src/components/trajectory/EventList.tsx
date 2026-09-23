import { useEffect, useMemo, useRef } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  ArrowDownToLine,
  Brain,
  Check,
  ChevronRight,
  CircleDot,
  Code2,
  FileText,
  Flag,
  GitBranch,
  MessageSquare,
  Terminal,
  X,
} from 'lucide-react'
import { rpc } from '@/lib/api'
import { cn, eventLabel } from '@/lib/utils'
import { useUI } from '@/stores/ui'
import { useClassifiers, useTimeline, useTrajectory } from '@/hooks/queries'
import { Empty, ErrorState, Loading } from '@/components/common/Primitives'
import type { EventSummary, Page } from '@/types/domain'
const PAGE = 100
export function EventIcon({
  type,
  size = 14,
}: {
  type: string
  size?: number
}) {
  const Icon =
    type === 'reasoning'
      ? Brain
      : type === 'tool_call'
        ? Terminal
        : type === 'tool_result'
          ? ArrowDownToLine
          : type === 'error'
            ? X
            : type === 'assistant'
              ? MessageSquare
              : type === 'user'
                ? CircleDot
                : type === 'score'
                  ? Check
                  : type === 'checkpoint'
                    ? Flag
                    : Code2
  return <Icon size={size} />
}
export function EventList() {
  const {
    trajectoryId,
    mode,
    expanded,
    range,
    selectedIndex,
    jumpVersion,
    select,
    set,
  } = useUI()
  const ref = useRef<HTMLDivElement>(null)
  const timeline = useTimeline(trajectoryId)
  const trajectory = useTrajectory(trajectoryId)
  const classifiers = useClassifiers()
  const base = useMemo(
    () => ({
      trajectoryId,
      mode,
      start: range?.start,
      end: range?.end,
      limit: PAGE,
    }),
    [trajectoryId, mode, range],
  )
  const first = useQuery({
    queryKey: ['events', base, 0],
    queryFn: () =>
      rpc<Page<EventSummary>>('events.list', { ...base, offset: 0 }),
    enabled: !!trajectoryId,
  })
  const virtualizer = useVirtualizer({
    count: first.data?.total || 0,
    getScrollElement: () => ref.current,
    estimateSize: () => (expanded ? 137 : 87),
    overscan: 5,
  })
  const virtualItems = virtualizer.getVirtualItems()
  const pages = [
    ...new Set(virtualItems.map((v) => Math.floor(v.index / PAGE))),
  ].filter((p) => p !== 0)
  const queries = useQueries({
    queries: pages.map((page) => ({
      queryKey: ['events', base, page],
      queryFn: () =>
        rpc<Page<EventSummary>>('events.list', {
          ...base,
          offset: page * PAGE,
        }),
    })),
  })
  const pageData = new Map<number, Page<EventSummary> | undefined>([
    [0, first.data],
    ...pages.map(
      (page, i) =>
        [page, queries[i].data] as [number, Page<EventSummary> | undefined],
    ),
  ])
  useEffect(() => {
    virtualizer.measure()
  }, [expanded, virtualizer])
  useEffect(() => {
    virtualizer.scrollToIndex(0)
  }, [trajectoryId, mode, range, virtualizer])
  useEffect(() => {
    if (mode === 'all' && !range && first.data)
      virtualizer.scrollToIndex(selectedIndex, { align: 'center' })
  }, [jumpVersion, trajectoryId, first.data?.total]) // selection alone must not hijack scrolling
  if (first.isLoading) return <Loading />
  if (first.error)
    return (
      <ErrorState
        error={first.error}
        retry={() => {
          void first.refetch()
        }}
      />
    )
  if (!first.data?.total)
    return (
      <Empty icon={<FileText />} title="No events in this view">
        Try another event filter or phase.
      </Empty>
    )
  return (
    <div className="event-scroll" ref={ref} data-testid="event-scroll">
      <div
        className="virtual-events"
        style={{ height: virtualizer.getTotalSize() }}
      >
        {virtualItems.map((row) => {
          const event = pageData.get(Math.floor(row.index / PAGE))?.items[
            row.index % PAGE
          ]
          if (!event)
            return (
              <div
                className="event-skeleton"
                key={row.index}
                style={{
                  height: row.size,
                  transform: `translateY(${row.start}px)`,
                }}
              >
                Loading events…
              </div>
            )
          const phase = timeline.data?.segments.find(
            (s) =>
              !s.parentId &&
              event.index >= s.startEvent &&
              event.index <= s.endEvent,
          )
          const annotated = timeline.data?.annotations.some(
            (a) =>
              event.index >= a.startEventIndex &&
              event.index <= a.endEventIndex,
          )
          const forked = timeline.data?.forks.some(
            (f) => f.sourceEventId === event.id,
          )
          const signals =
            timeline.data?.results.filter(
              (r) =>
                r.startEventIndex <= event.index &&
                r.endEventIndex >= event.index,
            ) || []
          return (
            <div
              key={event.id}
              className={cn(
                'event-row',
                selectedIndex === event.index && 'event-selected',
                expanded && 'event-expanded',
              )}
              style={{
                height: row.size,
                transform: `translateY(${row.start}px)`,
              }}
            >
              <button
                className="event-main"
                onClick={() => select(event.index)}
                onContextMenu={(e) => {
                  e.preventDefault()
                  select(event.index)
                  if (trajectory.data?.capabilities.contextOnly)
                    set({ modal: 'fork' })
                }}
              >
                <div className="event-gutter">
                  <span>{String(event.index).padStart(3, '0')}</span>
                  <div className={`event-type-icon type-${event.type}`}>
                    <EventIcon type={event.type} />
                  </div>
                  <i />
                </div>
                <div className="event-body">
                  <div className="event-topline">
                    <span className={`event-label type-${event.type}`}>
                      {event.toolName || eventLabel(event.type)}
                    </span>
                    {event.toolName && (
                      <span className="event-kind">
                        {event.type === 'tool_result' ? 'result' : 'tool call'}
                      </span>
                    )}
                    {event.hasError && <span className="error-tag">error</span>}
                    {phase && (
                      <span className="event-phase">{phase.label}</span>
                    )}
                    <span className="event-time">
                      {event.timestamp
                        ? new Date(event.timestamp).toLocaleTimeString([], {
                            hour12: false,
                          })
                        : `#${event.index}`}
                    </span>
                  </div>
                  <div
                    className={cn(
                      'event-preview',
                      (event.type === 'tool_call' ||
                        event.type === 'tool_result') &&
                        'mono',
                    )}
                  >
                    {event.preview || 'No text content · inspect the raw event'}
                  </div>
                  {expanded && (
                    <div className="expanded-meta">
                      {event.role || event.type}
                      <span>·</span>
                      {event.tokenUsage?.output
                        ? `${event.tokenUsage.output} output tokens`
                        : 'Open to inspect full event'}
                    </div>
                  )}
                </div>
                <div className="event-markers">
                  {annotated && (
                    <Flag size={11} className="annotation-marker" />
                  )}
                  {forked && <GitBranch size={12} />}{' '}
                  {signals.length > 0 && (
                    <span
                      className="signal-dot"
                      title={signals
                        .map((result) => {
                          const name =
                            classifiers.data?.find(
                              (c) => c.id === result.classifierId,
                            )?.name || result.classifierId
                          return `${name}: ${result.error ? 'classifier error' : result.output?.label || result.output?.score?.toFixed(2) || 'result available'}`
                        })
                        .join('\n')}
                    />
                  )}
                  <ChevronRight size={12} />
                </div>
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
