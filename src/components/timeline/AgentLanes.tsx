import { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useUI } from '@/stores/ui'
import type { TimelineData } from '@/types/domain'

export function AgentLanes({
  markers,
  total,
}: {
  markers: TimelineData['markers']
  total: number
}) {
  const groups = useMemo(() => {
    const result = new Map<string, number[]>()
    for (const event of markers)
      if (event.agent) {
        const points = result.get(event.agent) || []
        points.push(event.index)
        result.set(event.agent, points)
      }
    return [...result.entries()]
  }, [markers])
  const [open, setOpen] = useState(true)
  const ref = useRef<HTMLDivElement>(null)
  const virtual = useVirtualizer({
    count: groups.length,
    getScrollElement: () => ref.current,
    estimateSize: () => 26,
    overscan: 2,
  })
  if (!groups.length) return null
  return (
    <section className="agent-lanes">
      <button
        className="agent-lanes-heading"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? '▾' : '▸'} Agents · overview <span>{groups.length}</span>
      </button>
      {open && (
        <div
          ref={ref}
          className="agent-lanes-scroll"
          style={{ height: Math.min(104, groups.length * 26) }}
        >
          <div style={{ height: virtual.getTotalSize(), position: 'relative' }}>
            {virtual.getVirtualItems().map((row) => {
              const [name, points] = groups[row.index]
              return (
                <div
                  key={name}
                  className="agent-lane"
                  style={{
                    height: row.size,
                    transform: `translateY(${row.start}px)`,
                  }}
                >
                  <span title={name}>{name}</span>
                  <AgentTrack points={points} total={total} />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
function AgentTrack({ points, total }: { points: number[]; total: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const theme = useUI((s) => s.theme)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const draw = () => {
      const rect = canvas.getBoundingClientRect()
      canvas.width = rect.width * devicePixelRatio
      canvas.height = 22 * devicePixelRatio
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.scale(devicePixelRatio, devicePixelRatio)
      ctx.fillStyle = theme === 'dark' ? '#91ae7e' : '#557047'
      for (const index of points)
        ctx.fillRect(
          (index / Math.max(1, total - 1)) * (rect.width - 2),
          7,
          2,
          8,
        )
    }
    const observer = new ResizeObserver(draw)
    observer.observe(canvas)
    draw()
    return () => observer.disconnect()
  }, [points, total, theme])
  return (
    <canvas
      ref={ref}
      role="button"
      tabIndex={0}
      aria-label={`Agent events ${points[0]} to ${points.at(-1)}`}
      title="Click an agent event to inspect its parents and raw data"
      onClick={(e) => {
        const target =
          ((e.clientX - e.currentTarget.getBoundingClientRect().left) /
            e.currentTarget.clientWidth) *
          (total - 1)
        const index = points.reduce(
          (best, p) =>
            Math.abs(p - target) < Math.abs(best - target) ? p : best,
          points[0],
        )
        useUI.getState().jump(index)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') useUI.getState().jump(points[0])
      }}
    />
  )
}
