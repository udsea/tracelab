import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts/core'
import { CustomChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useUI } from '@/stores/ui'
import { useOverview, useSignals } from '@/features/analysis/queries'
import {
  activities as eventActivities,
  coordinateMap,
  type Scale,
} from '@/features/analysis/coordinates'
import { ExecutionGraph } from '@/features/analysis/ExecutionGraph'
import { ChevronDown } from 'lucide-react'
echarts.use([
  CustomChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer,
])
const palette = [
  '#9ebc8b',
  '#a6a1d6',
  '#cda270',
  '#72aeb6',
  '#d08794',
  '#85bcb0',
]
export function Timeline() {
  const ui = useUI(),
    overview = useOverview(ui.trajectoryId),
    signals = useSignals(ui.trajectoryId)
  const ref = useRef<HTMLDivElement>(null),
    chart = useRef<echarts.ECharts | null>(null)
  const [showRuntime, setShowRuntime] = useState(false)
  const [menu, setMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!menu) return
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenu(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setMenu(false)
      menuRef.current?.querySelector('button')?.focus()
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [menu])
  const [expanded, setExpanded] = useState(false)
  const latest = useRef({
    coords: coordinateMap([], 'events'),
    points: [] as import('@/types/analysis').CoordinatePoint[],
  })
  const points = overview.data?.coordinates.points ?? []
  const coords = useMemo(
    () => coordinateMap(points, ui.scale),
    [points, ui.scale],
  )
  latest.current = { coords, points }
  const signalLanes = [
    ...new Set(
      signals.data?.map((s) => String(s.metadata.laneId ?? s.name)) ?? [],
    ),
  ]
  const activities = [
    'Outline',
    'Model calls',
    'Reasoning',
    'Opaque reasoning',
    'Messages',
    'Tool calls',
    'Tool results',
    'Environment',
    'Artifacts',
    'Errors',
    'Scores',
    'Checkpoints',
    'Other',
    ...(showRuntime ? ['Runtime'] : []),
  ]
  const availableActivities = activities.filter(
    (l) =>
      l === 'Outline' || points.some((p) => eventActivities(p).includes(l)),
  )
  const lanes = [...availableActivities, ...signalLanes].filter(
    (l) => !ui.hiddenLanes.includes(l),
  )
  const height = Math.max(160, lanes.length * 24 + 34)
  useEffect(() => {
    if (!ref.current) return
    const instance = echarts.init(ref.current, undefined, {
      renderer: 'canvas',
    })
    chart.current = instance
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(ref.current)
    instance.on('click', (raw: unknown) => {
      const p = raw as {
        data?: {
          eventIndex?: number
          signalId?: string
          range?: [number, number]
          name?: string
        }
      }
      if (p.data?.range) {
        ui.focus(...p.data.range, p.data.name ?? 'Outline')
        return
      }
      if (p.data?.eventIndex != null) ui.jump(p.data.eventIndex)
      if (p.data?.signalId) ui.set({ signalId: p.data.signalId })
    })
    let zoomTimer: ReturnType<typeof setTimeout> | undefined
    instance.on('datazoom', (raw: unknown) => {
      const payload = raw as {
        start?: number
        end?: number
        batch?: { start?: number; end?: number }[]
      }
      const zoom = payload.batch?.[0] ?? payload
      if (zoom.start == null || zoom.end == null) return
      clearTimeout(zoomTimer)
      zoomTimer = setTimeout(() => {
        const { coords: current, points: all } = latest.current
        const matched = all.filter(
          (p) =>
            current.at(p.index) >= (zoom.start! / 100) * current.max &&
            current.at(p.index) <= (zoom.end! / 100) * current.max,
        )
        if (matched.length)
          ui.focus(
            matched.reduce((min, p) => Math.min(min, p.index), Infinity),
            matched.reduce((max, p) => Math.max(max, p.index), -Infinity),
            'Timeline zoom',
          )
      }, 150)
    })
    instance.getZr().on('click', (event) => {
      if (event.target) return
      const coordinate = instance.convertFromPixel(
        { xAxisIndex: 0 },
        event.offsetX,
      ) as number
      if (Number.isFinite(coordinate))
        ui.jump(latest.current.coords.nearest(coordinate))
    })
    return () => {
      clearTimeout(zoomTimer)
      observer.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [ui.trajectoryId])
  useEffect(() => {
    const instance = chart.current
    if (!instance) return
    const [start, end] = ui.range
      ? coords.extent(ui.range.start, ui.range.end)
      : [0, coords.max]
    const visible = points.filter(
      (p) =>
        (showRuntime || p.presentationClass !== 'runtime') &&
        (!ui.range || (p.index >= ui.range.start && p.index <= ui.range.end)),
    )
    const buckets = new Map<
      string,
      { value: number[]; eventIndex: number; count: number; name: string }
    >()
    const aggregate = visible.length > 300
    for (const p of visible) {
      for (const lane of eventActivities(p)) {
        const y = lanes.indexOf(lane)
        if (y < 0) continue
        const x = coords.at(p.index),
          bucket = aggregate
            ? Math.floor(((x - start) / Math.max(1, end - start)) * 180)
            : p.index
        const key = `${y}:${bucket}`
        const old = buckets.get(key)
        if (old) old.count++
        else
          buckets.set(key, {
            value: [x, y],
            eventIndex: p.index,
            count: 1,
            name: `${lane} · #${p.index}${p.elapsedMs === null && ui.scale === 'time' ? ' · timestamp unavailable' : ''}`,
          })
      }
    }
    const intervals = (signals.data ?? [])
      .filter((s) => lanes.includes(String(s.metadata.laneId ?? s.name)))
      .map((s) => ({
        value: [
          Math.min(coords.at(s.startEventIndex), coords.at(s.endEventIndex)),
          lanes.indexOf(String(s.metadata.laneId ?? s.name)),
          Math.max(coords.at(s.startEventIndex), coords.at(s.endEventIndex)),
        ],
        signalId: s.id,
        eventIndex: s.startEventIndex,
        name: `${s.name} · #${s.startEventIndex}–${s.endEventIndex} · ${s.score ?? s.label ?? 'unscored'}`,
        itemStyle: {
          color:
            palette[
              signalLanes.indexOf(String(s.metadata.laneId ?? s.name)) %
                palette.length
            ],
          opacity:
            s.score == null
              ? 0.65
              : 0.35 + Math.min(1, Math.abs(s.score)) * 0.65,
        },
      }))
    const structure = (overview.data?.outline ?? [])
      .filter(
        (n) =>
          lanes.includes('Outline') &&
          (n.kind === 'segment' || n.kind === 'episode' || n.kind === 'moment'),
      )
      .map((n) => ({
        value: [
          Math.min(coords.at(n.startEventIndex), coords.at(n.endEventIndex)),
          lanes.indexOf('Outline'),
          Math.max(coords.at(n.startEventIndex), coords.at(n.endEventIndex)),
        ],
        range: [n.startEventIndex, n.endEventIndex],
        name: `${n.kind}: ${n.label}`,
        itemStyle: {
          color: n.kind === 'moment' ? '#d08794' : '#648778',
          opacity: 0.5,
        },
      }))
    instance.setOption(
      {
        animation: false,
        grid: { left: 170, right: 30, top: 8, bottom: 26 },
        xAxis: {
          type: 'value',
          min: 0,
          max: coords.max,
          axisLabel: {
            color: '#8b978e',
            fontSize: 10,
            formatter: (v: number) =>
              ui.scale === 'time'
                ? v > coords.maxTime
                  ? 'untimed'
                  : `${(v / 1000).toFixed(0)}s`
                : String(Math.round(v)),
          },
          splitLine: { show: false },
        },
        yAxis: {
          type: 'category',
          inverse: true,
          data: lanes.map(
            (l) =>
              signals.data?.find(
                (s) => String(s.metadata.laneId ?? s.name) === l,
              )?.name ?? l,
          ),
          axisLabel: {
            color: '#8b978e',
            fontSize: 10,
            width: 150,
            overflow: 'truncate',
          },
          axisTick: { show: false },
          axisLine: { show: false },
        },
        tooltip: {
          trigger: 'item',
          renderMode: 'richText',
          formatter: (p: { data: { name: string; count?: number } }) =>
            `${p.data.name}${p.data.count && p.data.count > 1 ? ` · ${p.data.count} events in bin` : ''}`,
        },
        dataZoom: [
          {
            type: 'inside',
            startValue: start,
            endValue: Math.max(start + 0.01, end),
            zoomOnMouseWheel: 'ctrl',
            moveOnMouseWheel: false,
            filterMode: 'weak',
          },
        ],
        series: [
          {
            type: 'scatter',
            symbol: 'rect',
            symbolSize: aggregate ? [5, 12] : [3, 12],
            data: [...buckets.values()],
            itemStyle: { color: '#789882' },
            markLine: {
              silent: true,
              symbol: 'none',
              label: { show: false },
              data: [{ xAxis: coords.at(ui.selectedIndex) }],
            },
          },
          {
            type: 'custom',
            renderItem: (
              _params: unknown,
              api: {
                value: (i: number) => number
                coord: (v: number[]) => number[]
                style: () => object
              },
            ) => {
              const a = api.coord([api.value(0), api.value(1)]),
                b = api.coord([api.value(2), api.value(1)])
              return {
                type: 'rect',
                shape: {
                  x: a[0],
                  y: a[1] - 6,
                  width: Math.max(3, b[0] - a[0]),
                  height: 12,
                },
                style: api.style(),
              }
            },
            encode: { x: [0, 2], y: 1 },
            data: [...structure, ...intervals],
          },
        ],
      },
      true,
    )
    instance.resize()
  }, [
    overview.data,
    signals.data,
    ui.range,
    ui.scale,
    ui.hiddenLanes,
    ui.selectedIndex,
    height,
    showRuntime,
  ])
  function zoomAroundSelection() {
    const width = Math.max(
      10,
      ((ui.range?.end ?? points.length - 1) - (ui.range?.start ?? 0)) / 2,
    )
    ui.focus(
      Math.max(0, Math.floor(ui.selectedIndex - width / 2)),
      Math.min(points.length - 1, Math.ceil(ui.selectedIndex + width / 2)),
      'Zoom around selection',
    )
  }
  if (!ui.trajectoryId) return null
  return (
    <section
      className="timeline-panel"
      style={expanded ? { height: '48vh' } : undefined}
    >
      <div className="timeline-heading">
        <strong title={`${points.length} recorded events`}>
          Overview · {overview.data?.eventCounts.research ?? points.length}{' '}
          research events
        </strong>
        <div className="timeline-controls">
          <select
            aria-label="Timeline scale"
            value={ui.scale}
            onChange={(e) => ui.set({ scale: e.target.value as Scale })}
          >
            <option value="events">Events</option>
            <option value="time">Elapsed time</option>
            <option value="calls">Model calls</option>
          </select>
          {ui.rangeHistory.length > 0 && (
            <button onClick={() => ui.backRange()}>Previous range</button>
          )}
          <button
            onClick={() =>
              ui.focus(0, Math.max(0, points.length - 1), 'Full run')
            }
            title="Show the full run"
          >
            Reset
          </button>
          <div className="view-menu" ref={menuRef}>
            <button
              aria-haspopup="true"
              aria-expanded={menu}
              aria-controls="timeline-view-menu"
              onClick={() => setMenu(!menu)}
            >
              View
              <ChevronDown size={11} aria-hidden />
            </button>
            {menu && (
              <div
                id="timeline-view-menu"
                className="view-menu-popover"
                role="group"
                aria-label="Timeline view options"
              >
                <div className="view-menu-actions">
                  <button onClick={zoomAroundSelection}>
                    Zoom around #{ui.selectedIndex}
                  </button>
                  <button onClick={() => setExpanded(!expanded)}>
                    {expanded ? 'Collapse panel' : 'Expand panel'}
                  </button>
                  <button
                    onClick={() =>
                      ui.set({
                        hiddenLanes: [
                          ...new Set([...ui.hiddenLanes, ...activities]),
                        ],
                      })
                    }
                  >
                    Signals only
                  </button>
                  <button onClick={() => ui.set({ hiddenLanes: [] })}>
                    All lanes
                  </button>
                </div>
                <label className="view-menu-check">
                  <input
                    type="checkbox"
                    checked={showRuntime}
                    onChange={(e) => setShowRuntime(e.target.checked)}
                  />
                  Include runtime events
                </label>
                <fieldset>
                  <legend>Lanes</legend>
                  {[...availableActivities, ...signalLanes].map((l) => (
                    <label key={l} className="view-menu-check">
                      <input
                        type="checkbox"
                        checked={!ui.hiddenLanes.includes(l)}
                        onChange={() =>
                          ui.set({
                            hiddenLanes: ui.hiddenLanes.includes(l)
                              ? ui.hiddenLanes.filter((x) => x !== l)
                              : [...ui.hiddenLanes, l],
                          })
                        }
                      />
                      {signals.data?.find(
                        (s) => String(s.metadata.laneId ?? s.name) === l,
                      )?.name ?? l}
                    </label>
                  ))}
                </fieldset>
                <p className="muted small" id="timeline-gestures">
                  Ctrl + scroll zooms the chart, drag pans it, and clicking a
                  mark selects its event.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
      {ui.scale === 'time' && coords.hasGutter && (
        <p className="timeline-fidelity">
          {overview.data?.coordinates.missingTimestamps} untimed events in
          ordinal gutter after the time axis; no timestamps inferred.
        </p>
      )}
      {ui.scale === 'calls' && (
        <p className="timeline-fidelity">
          {overview.data?.coordinates.modelCallFidelity}
        </p>
      )}
      {overview.error && (
        <p className="inline-error">{overview.error.message}</p>
      )}
      <div className="timeline-scroll">
        <div
          ref={ref}
          style={{ height }}
          role="img"
          aria-label="Trajectory timeline. Ctrl + scroll zooms, drag pans, clicking a mark selects its event."
        />
        {overview.data && <ExecutionGraph overview={overview.data} />}
      </div>
    </section>
  )
}
