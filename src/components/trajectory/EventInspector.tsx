import { ToolOrigin } from '@/features/forks/ExecutionOptions'
import { presentationLabel, opaqueDescription } from './presentation'
import type {
  ReasoningVisibility,
  EventPresentationClass,
} from '@/types/domain'
import { AnalysisStack } from '@/features/analysis/SignalInspector'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowUpRight,
  Braces,
  Check,
  Copy,
  FileJson2,
  Flag,
  FlaskConical,
  GitBranch,
  Info,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useUI, notify } from '@/stores/ui'
import { rpc } from '@/lib/api'
import { json } from '@/lib/utils'
import { useClassifiers, useTimeline, useTrajectory } from '@/hooks/queries'
import { Empty, ErrorState, Loading } from '@/components/common/Primitives'
import { EventIcon } from './EventList'
import { EventRelations } from './EventRelations'
import type { ClassifierResult, TrajectoryEvent } from '@/types/domain'
export function EventInspector() {
  const ui = useUI()
  const [tab, setTab] = useState('event')
  const [rawEventId, setRawEventId] = useState<string | null>(null)
  const trajectory = useTrajectory(ui.trajectoryId)
  const query = useQuery({
    queryKey: ['event', ui.trajectoryId, ui.selectedIndex],
    queryFn: () =>
      rpc<{ event: TrajectoryEvent; results: ClassifierResult[] }>(
        'events.get',
        { trajectoryId: ui.trajectoryId, index: ui.selectedIndex },
      ),
    enabled: !!ui.trajectoryId,
  })
  const id = query.data?.event.id
  const rawOpen = !!id && rawEventId === id
  const setRawOpen = (open: boolean) => setRawEventId(open && id ? id : null)
  const raw = useQuery({
    queryKey: ['raw-event', id],
    queryFn: () => rpc('events.raw', { id }),
    enabled: !!id && rawOpen,
  })
  const timeline = useTimeline(ui.trajectoryId)
  const classifiers = useClassifiers()
  const data = query.data
  const event = data?.event
  const annotations =
    timeline.data?.annotations.filter(
      (a) =>
        a.startEventIndex <= ui.selectedIndex &&
        a.endEventIndex >= ui.selectedIndex,
    ) || []
  const origins =
    timeline.data?.forks.filter((f) => f.sourceEventId === id) || []
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value)
      notify('Copied to clipboard')
    } catch {
      notify('Clipboard access was unavailable.')
    }
  }
  return (
    <aside className="inspector">
      <div className="inspector-header">
        <span>INSPECTOR</span>
        <span className="selected-event-tag">EVENT #{ui.selectedIndex}</span>
      </div>
      <div className="inspector-tabs">
        {[
          ['event', 'Event'],
          ['signals', 'Signals'],
          [
            'notes',
            `Notes${annotations.length ? ` ${annotations.length}` : ''}`,
          ],
        ].map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? 'active' : ''}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="inspector-content">
        {query.isLoading && <Loading text="Loading event…" />}
        {query.error && <ErrorState error={query.error} />}
        {!id && <Empty title="No event selected" />}
        {event && tab === 'event' && (
          <>
            <div className="inspector-event-type">
              <span className={`event-type-icon type-${event.type}`}>
                <EventIcon type={event.type} size={17} />
              </span>
              <div>
                <h3>
                  {event.tool?.name ||
                    presentationLabel(
                      event.type,
                      event.metadata.reasoningVisibility as ReasoningVisibility,
                    )}
                </h3>
                <span>
                  {presentationLabel(
                    event.type,
                    event.metadata.reasoningVisibility as ReasoningVisibility,
                  )}
                  <span className="muted"> · #{event.index}</span>
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                title="Copy content"
                onClick={() => {
                  void copy(event.content || json(event.tool))
                }}
              >
                <Copy size={14} />
              </Button>
            </div>
            <ToolOrigin metadata={event.metadata} />
            <div className="inspector-meta">
              <span>Role</span>
              <span>{event.role || '—'}</span>
              <span>Timestamp</span>
              <span>
                {event.timestamp
                  ? new Date(event.timestamp).toLocaleTimeString([], {
                      hour12: false,
                    })
                  : 'Not recorded'}
              </span>
              {event.tokenUsage && (
                <>
                  <span>Tokens · in / out</span>
                  <span>
                    {event.tokenUsage.input ?? '—'} /{' '}
                    {event.tokenUsage.output ?? '—'}
                  </span>
                </>
              )}
            </div>
            <EventRelations event={event} />
            {event.metadata.presentationClass === 'runtime' && (
              <p className="muted">
                Runtime record · preserved framework activity, excluded from
                default research analysis.
              </p>
            )}
            {event.tool?.arguments != null && (
              <>
                <div className="detail-heading">
                  ARGUMENTS
                  <Braces size={12} />
                </div>
                <pre className="code-block">{json(event.tool.arguments)}</pre>
              </>
            )}
            <div className="detail-heading">
              {event.type === 'reasoning'
                ? 'REASONING'
                : event.type === 'tool_result'
                  ? 'TOOL OUTPUT'
                  : 'CONTENT'}
              <Button
                variant="ghost"
                size="icon"
                title="Copy event JSON"
                onClick={() => {
                  void copy(json(event))
                }}
              >
                <FileJson2 size={12} />
              </Button>
            </div>
            {event.metadata.presentationClass === 'opaque' ? (
              <div className="inspector-callout">
                <p>
                  {opaqueDescription(
                    event.metadata.presentationClass as EventPresentationClass,
                  )}
                </p>
                <button onClick={() => setRawOpen(true)}>
                  Show raw payload
                </button>
              </div>
            ) : (event.content?.length || 0) > 1800 ? (
              <details className="raw-details">
                <summary>
                  Show large output · {event.content?.length.toLocaleString()}{' '}
                  characters
                </summary>
                <pre>{event.content}</pre>
              </details>
            ) : (
              <pre
                className={`content-block ${event.type === 'reasoning' || event.type === 'assistant' ? 'prose-content' : ''}`}
              >
                {event.content || '(No text content)'}
              </pre>
            )}
            {event.tool?.error && (
              <div className="inline-error">{event.tool.error}</div>
            )}
            <div className="inspector-separator" />
            <AnalysisStack />
            <details className="raw-details">
              <summary>Event metadata</summary>
              <pre>{json(event.metadata)}</pre>
            </details>
            <details
              className="raw-details"
              open={rawOpen}
              onToggle={(e) => setRawOpen(e.currentTarget.open)}
            >
              <summary>
                <FileJson2 size={12} />
                Open raw source record
              </summary>
              <pre>
                {raw.isLoading
                  ? 'Loading…'
                  : raw.error
                    ? raw.error.message
                    : json(raw.data)}
              </pre>
            </details>
            {origins.length > 0 && (
              <>
                <div className="detail-heading">FORKS FROM HERE</div>
                {origins.map((f) => (
                  <button
                    className="text-row"
                    key={f.id}
                    onClick={() => ui.set({ section: 'forks' })}
                  >
                    <GitBranch size={13} />
                    {f.childTrajectoryIds.length} branches{' '}
                    <span>{f.status}</span>
                  </button>
                ))}
              </>
            )}
          </>
        )}
        {tab === 'signals' && (
          <>
            <AnalysisStack />
            <SignalList
              results={data?.results || []}
              names={new Map(classifiers.data?.map((c) => [c.id, c.name]))}
            />
            <div className="inspector-callout">
              <Info size={14} />
              <p>
                Classifier outputs are hypotheses. Inspect the cited events and
                rationale before drawing a conclusion.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => ui.openAnalysis('signals/semantic')}
            >
              <FlaskConical size={13} />
              Configure detectors
            </Button>
          </>
        )}
        {tab === 'notes' && (
          <>
            <div className="detail-heading">MANUAL ANNOTATIONS</div>
            {annotations.length === 0 ? (
              <p className="muted">
                No annotations at this event. Use Annotate below to mark a
                finding or a range to revisit.
              </p>
            ) : (
              annotations.map((a) => (
                <div className="annotation-note" key={a.id}>
                  <span>
                    <Flag size={12} />
                    {a.label}
                    <small>
                      #{a.startEventIndex}–{a.endEventIndex}
                    </small>
                  </span>
                  <p>{a.note}</p>
                </div>
              ))
            )}
          </>
        )}
      </div>
      {event && (
        <div className="inspector-actions">
          <Button
            variant="outline"
            size="sm"
            onClick={() => ui.set({ modal: 'annotate' })}
          >
            <Flag size={13} />
            Annotate
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!trajectory.data?.capabilities.contextOnly}
            title={
              trajectory.data?.capabilities.contextOnly
                ? `Fork a context-only branch from event #${ui.selectedIndex} (F)`
                : trajectory.data?.capabilities.reason
            }
            onClick={() => ui.set({ modal: 'fork' })}
          >
            <GitBranch size={13} />
            Fork from #{ui.selectedIndex}
          </Button>
        </div>
      )}
    </aside>
  )
}
function SignalList({
  results,
  names,
}: {
  results: ClassifierResult[]
  names: Map<string, string>
}) {
  const set = useUI((s) => s.set)
  const unique = results.filter(
    (r, i) => results.findIndex((x) => x.classifierId === r.classifierId) === i,
  )
  return (
    <>
      <div className="detail-heading">
        CLASSIFIER SIGNALS<span className="tiny-count">{unique.length}</span>
      </div>
      {!unique.length && (
        <p className="muted inspector-empty">
          No classifier results at this event.
        </p>
      )}
      {unique.map((r, i) => (
        <button
          className="signal-card"
          key={r.id}
          onClick={() => set({ resultId: r.id })}
        >
          <div>
            <span className={`lane-dot lane-${i % 4}`} />
            <span>{names.get(r.classifierId) || r.classifierId}</span>
            <strong>{r.output?.score?.toFixed(2) ?? '—'}</strong>
          </div>
          <div className="signal-meter">
            <i
              className={`lane-bg-${i % 4}`}
              style={{ width: `${(r.output?.score || 0) * 100}%` }}
            />
          </div>
          <footer>
            <span>
              {r.error
                ? 'Classifier error'
                : r.output?.label || 'View rationale'}
              {r.cached && <Check size={10} />}
            </span>
            <span>
              Evidence
              <ArrowUpRight size={11} />
            </span>
          </footer>
        </button>
      ))}
    </>
  )
}
