import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { rpc } from '@/lib/api'
import { useUI } from '@/stores/ui'
import type { Overview, Relationship } from '@/types/analysis'
import type { TrajectoryEvent } from '@/types/domain'
import { coordinateMap } from './coordinates'
export function ExecutionGraph({ overview }: { overview: Overview }) {
  const ui = useUI(),
    [graph, setGraph] = useState(false),
    [edge, setEdge] = useState<Relationship | null>(null)
  const points = overview.coordinates.points,
    agents = useMemo(
      () => [
        ...new Set(
          [
            ...points.map((p) => p.agent),
            ...overview.relationships.flatMap((e) => [
              e.sourceAgent,
              e.destinationAgent,
            ]),
          ].filter((a): a is string => !!a),
        ),
      ],
      [points, overview.relationships],
    )
  const map = coordinateMap(points, ui.scale)
  const [start, end] = ui.range
    ? map.extent(ui.range.start, ui.range.end)
    : [0, map.max]
  const x = (index: number) =>
    150 +
    Math.max(
      0,
      Math.min(1, (map.at(index) - start) / Math.max(1, end - start)),
    ) *
      800
  const y = (agent: string) => 25 + agents.indexOf(agent) * 32
  const evidence = useQuery({
    queryKey: ['relationship', edge?.id],
    queryFn: () =>
      Promise.all(
        [...new Set([edge!.sourceEventId, edge!.destinationEventId])].map(
          (id) => rpc<{ event: TrajectoryEvent }>('events.get', { id }),
        ),
      ),
    enabled: !!edge,
  })
  const allEdges = overview.relationships.filter(
    (e) =>
      !ui.range ||
      (e.sourceIndex >= ui.range.start && e.sourceIndex <= ui.range.end) ||
      (e.destinationIndex >= ui.range.start &&
        e.destinationIndex <= ui.range.end),
  )
  const [edgePage, setEdgePage] = useState(0)
  const edgeOffset = Math.min(
    edgePage * 200,
    Math.max(0, Math.floor((allEdges.length - 1) / 200) * 200),
  )
  const edges = allEdges.slice(edgeOffset, edgeOffset + 200)
  const visiblePoints = points.filter(
    (p) =>
      p.presentationClass !== 'runtime' &&
      p.agent &&
      (!ui.range || (p.index >= ui.range.start && p.index <= ui.range.end)),
  )
  const bins = new Map<
    string,
    { point: (typeof points)[number]; count: number }
  >()
  for (const point of visiblePoints) {
    const key =
      visiblePoints.length > 400
        ? `${point.agent}:${Math.floor(x(point.index) / 5)}`
        : point.id
    const existing = bins.get(key)
    if (existing) existing.count++
    else bins.set(key, { point, count: 1 })
  }
  if (!agents.length) return null
  return (
    <section className="execution-view">
      <div className="timeline-heading">
        <strong>Agents · recorded structure</strong>
        <button onClick={() => setGraph(!graph)}>
          {graph ? 'Execution lanes' : 'Information graph'}
        </button>
      </div>
      <div style={{ maxHeight: 180, overflow: 'auto' }}>
        <svg
          viewBox={`0 0 1000 ${Math.max(70, agents.length * 32 + 20)}`}
          style={{ width: '100%', minWidth: 600 }}
          role="img"
          aria-label="Agent activity and recorded relationships"
        >
          <defs>
            <marker
              id="relation-arrow"
              markerWidth="6"
              markerHeight="6"
              refX="5"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6" fill="#a6a1d6" />
            </marker>
          </defs>
          {agents.map((a, i) => (
            <g key={a}>
              <text x={5} y={y(a) + 4} fill="currentColor" fontSize={11}>
                {a.slice(0, 22)}
              </text>
              {graph ? (
                <circle
                  cx={220 + (i % 2) * 400}
                  cy={y(a)}
                  r={7}
                  fill="#9ebc8b"
                />
              ) : (
                <line
                  x1={150}
                  x2={950}
                  y1={y(a)}
                  y2={y(a)}
                  stroke="#657568"
                  opacity={0.25}
                />
              )}
            </g>
          ))}
          {!graph &&
            [...bins.values()].map(({ point: p, count }) => (
              <line
                key={p.id}
                x1={x(p.index)}
                x2={x(p.index)}
                y1={y(p.agent!) - 4}
                y2={y(p.agent!) + 4}
                stroke="#9ebc8b"
                onClick={() => ui.jump(p.index)}
              >
                <title>
                  {p.agent} · #{p.index} · {count} events in bin
                </title>
              </line>
            ))}
          {edges.map((e) => (
            <path
              key={e.id}
              d={
                graph
                  ? `M${220 + (agents.indexOf(e.sourceAgent) % 2) * 400},${y(e.sourceAgent)} Q800,${(y(e.sourceAgent) + y(e.destinationAgent)) / 2} ${220 + (agents.indexOf(e.destinationAgent) % 2) * 400},${y(e.destinationAgent)}`
                  : `M${x(e.sourceIndex)},${y(e.sourceAgent)} L${x(e.destinationIndex)},${y(e.destinationAgent)}`
              }
              fill="none"
              stroke="#a6a1d6"
              strokeWidth={2}
              strokeDasharray={e.kind === 'shared_artifact' ? '4 3' : undefined}
              markerEnd={
                e.kind === 'shared_artifact'
                  ? undefined
                  : 'url(#relation-arrow)'
              }
              onClick={() => setEdge(e)}
              tabIndex={0}
              role="button"
              onKeyDown={(k) => {
                if (k.key === 'Enter') setEdge(e)
              }}
            >
              <title>
                {e.description} · #{e.sourceIndex} → #{e.destinationIndex}
              </title>
            </path>
          ))}
        </svg>
      </div>
      {edges.length > 0 && (
        <label className="field">
          Recorded relationship
          <select
            value={edge?.id ?? ''}
            onChange={(e) =>
              setEdge(edges.find((row) => row.id === e.target.value) ?? null)
            }
          >
            <option value="">Select source and destination evidence</option>
            {edges.map((e) => (
              <option key={e.id} value={e.id}>
                {e.sourceAgent} → {e.destinationAgent} · #{e.sourceIndex} / #
                {e.destinationIndex} · {e.kind}
              </option>
            ))}
          </select>
        </label>
      )}
      {allEdges.length > 200 && (
        <div>
          <button
            disabled={edgeOffset === 0}
            onClick={() => setEdgePage(Math.max(0, edgePage - 1))}
          >
            Previous relationships
          </button>
          <span>
            {' '}
            {edgeOffset + 1}–{Math.min(edgeOffset + 200, allEdges.length)} /{' '}
            {allEdges.length} recorded relationships{' '}
          </span>
          <button
            disabled={edgeOffset + 200 >= allEdges.length}
            onClick={() => setEdgePage(edgePage + 1)}
          >
            Next relationships
          </button>
        </div>
      )}
      {!edges.length && (
        <p className="muted">
          No recorded cross-agent relationships in this range.
        </p>
      )}
      {edge && (
        <div className="relationship-evidence">
          <button onClick={() => setEdge(null)}>Close relationship</button>
          <p>{edge.description}</p>
          {evidence.data?.map(({ event }) => (
            <button key={event.id} onClick={() => ui.jump(event.index)}>
              <strong>
                #{event.index} ·{' '}
                {String(event.metadata.agentId ?? event.role ?? event.type)}
              </strong>
              <pre>
                {event.content?.slice(0, 1200) ||
                  JSON.stringify(event.tool, null, 2)}
              </pre>
            </button>
          ))}
          {evidence.error && <p>{evidence.error.message}</p>}
        </div>
      )}
    </section>
  )
}
