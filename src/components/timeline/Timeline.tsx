import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts/core'
import { LineChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  ChevronDown,
  Crosshair,
  Layers3,
  Minus,
  Plus,
  RotateCcw,
} from 'lucide-react'
import { useClassifiers, useTimeline, useTrajectory } from '@/hooks/queries'
import { useUI } from '@/stores/ui'
import { Button } from '@/components/ui/button'
import { AgentLanes } from './AgentLanes'
echarts.use([
  LineChart,
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
const escapeHtml = (value: string) =>
  value.replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[
        c
      ]!,
  )
export function Timeline() {
  const ui = useUI()
  const query = useTimeline(ui.trajectoryId)
  const trajectory = useTrajectory(ui.trajectoryId)
  const classifiers = useClassifiers()
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const [menu, setMenu] = useState(false)
  const [zoom, setZoom] = useState(100)
  const data = query.data
  const total = trajectory.data?.trajectory.eventCount || 1
  const lanes = useMemo(
    () =>
      [...new Set(data?.results.map((r) => r.classifierId) || [])].map(
        (id) => ({
          id,
          label: classifiers.data?.find((c) => c.id === id)?.name || id,
        }),
      ),
    [data, classifiers.data],
  )
  const visible = lanes.filter((l) => !ui.hiddenLanes.includes(l.id))
  const height = 55 + visible.length * 35
  useEffect(() => {
    if (!ref.current) return
    const instance = echarts.init(ref.current, undefined, {
      renderer: 'canvas',
    })
    chart.current = instance
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(ref.current)
    instance.on('click', (params: unknown) => {
      const point = params as {
        data?: { value?: number[]; resultId?: string } | number[]
      }
      if (Array.isArray(point.data)) ui.jump(Math.round(point.data[0]))
      else if (point.data?.value) {
        ui.jump(Math.round(point.data.value[0]))
        if (point.data.resultId) ui.set({ resultId: point.data.resultId })
      }
    })
    instance.getZr().on('click', (event) => {
      if (!event.target && chart.current) {
        const point = chart.current.convertFromPixel(
          { xAxisIndex: 0 },
          event.offsetX,
        ) as number
        if (Number.isFinite(point))
          ui.jump(Math.max(0, Math.min(total - 1, Math.round(point))))
      }
    })
    return () => {
      observer.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [ui.trajectoryId, total])
  useEffect(() => {
    if (!chart.current || !data) return
    const muted = ui.theme === 'dark' ? '#68716c' : '#727970'
    const grids = Array.from({ length: visible.length + 1 }, (_, i) => ({
      left: 167,
      right: 30,
      top: i * 35 + 9,
      height: 23,
      containLabel: false,
    }))
    const axes = grids.map((_, i) => ({
      type: 'value',
      min: 0,
      max: total - 1,
      gridIndex: i,
      show: i === visible.length,
      axisLabel: { color: muted, fontSize: 9, margin: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
    }))
    const series: unknown[] = [
      {
        name: 'Events',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbolSize: [2, 9],
        data: data.markers
          .filter(
            (m) =>
              ['tool_call', 'error', 'checkpoint'].includes(m.type) || m.error,
          )
          .map((m) => ({
            value: [m.index, 0.5],
            itemStyle: {
              color: m.error || m.type === 'error' ? '#d98782' : '#648778',
            },
            symbol: m.error ? 'triangle' : 'rect',
          })),
      },
    ]
    visible.forEach((lane, i) => {
      const items = data.results.filter((r) => r.classifierId === lane.id)
      series.push({
        name: lane.label,
        type: 'line',
        xAxisIndex: i + 1,
        yAxisIndex: i + 1,
        symbol: 'circle',
        symbolSize: 3,
        smooth: false,
        connectNulls: false,
        lineStyle: { width: 1.5, color: palette[i % palette.length] },
        itemStyle: { color: palette[i % palette.length] },
        areaStyle: { color: palette[i % palette.length], opacity: 0.09 },
        data: items.map((r) => ({
          value: [r.startEventIndex, r.output?.score ?? null],
          resultId: r.id,
          end: r.endEventIndex,
          label: r.error ? 'Classifier error' : r.output?.label || '',
        })),
        markLine: {
          silent: true,
          symbol: 'none',
          label: { show: false },
          lineStyle: { color: '#b5c7ad', opacity: 0.35, width: 1 },
          data: [{ xAxis: ui.selectedIndex }],
        },
      })
    })
    chart.current.setOption(
      {
        animation: false,
        grid: grids,
        xAxis: axes,
        yAxis: grids.map((_, i) => ({
          type: 'value',
          min: 0,
          max: 1,
          gridIndex: i,
          show: false,
        })),
        tooltip: {
          trigger: 'item',
          backgroundColor: ui.theme === 'dark' ? '#222923' : '#fff',
          borderColor: '#52604f',
          textStyle: {
            color: ui.theme === 'dark' ? '#d9e3d5' : '#1c2b1c',
            fontSize: 11,
          },
          formatter: (p: {
            seriesName: string
            data: { value: number[]; end?: number; label?: string }
          }) =>
            `${escapeHtml(p.seriesName)}<br/>Events ${p.data.value[0]}${p.data.end != null ? `–${p.data.end}` : ''}${p.data.end != null ? `<br/>Score: ${p.data.value[1]} · ${escapeHtml(p.data.label || '')}<br/>Click to inspect evidence` : ''}`,
        },
        dataZoom: [
          {
            type: 'inside',
            xAxisIndex: grids.map((_, i) => i),
            start: Math.max(
              0,
              Math.min(100 - zoom, (ui.selectedIndex / total) * 100 - zoom / 2),
            ),
            end: Math.min(
              100,
              Math.max(zoom, (ui.selectedIndex / total) * 100 + zoom / 2),
            ),
            zoomOnMouseWheel: 'ctrl',
            moveOnMouseWheel: false,
          },
        ],
        series,
      },
      true,
    )
    chart.current.resize()
  }, [
    data,
    visible.map((v) => v.id).join(','),
    ui.selectedIndex,
    ui.theme,
    total,
    zoom,
    height,
  ])
  if (!ui.trajectoryId) return null
  return (
    <section className="timeline-panel">
      <div className="timeline-heading">
        <div>
          <Crosshair size={14} />
          <strong>Trajectory timeline</strong>
          <span>{total} events</span>
        </div>
        <div>
          <span className="timeline-hint">
            Click to navigate · Ctrl + scroll to zoom
          </span>
          <Button
            variant="ghost"
            size="icon"
            title="Zoom out"
            onClick={() => setZoom((z) => Math.min(100, z * 1.5))}
          >
            <Minus size={13} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="Zoom in"
            onClick={() => setZoom((z) => Math.max(5, z / 1.5))}
          >
            <Plus size={13} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="Reset zoom"
            onClick={() => setZoom(100)}
          >
            <RotateCcw size={12} />
          </Button>
          <div className="lane-picker">
            <button
              className="lane-picker-button"
              onClick={() => setMenu(!menu)}
            >
              <Layers3 size={12} />
              Lanes
              <ChevronDown size={12} />
            </button>
            {menu && (
              <div className="lane-menu">
                {lanes.map((l) => (
                  <label key={l.id}>
                    <input
                      type="checkbox"
                      checked={!ui.hiddenLanes.includes(l.id)}
                      onChange={() =>
                        ui.set({
                          hiddenLanes: ui.hiddenLanes.includes(l.id)
                            ? ui.hiddenLanes.filter((x) => x !== l.id)
                            : [...ui.hiddenLanes, l.id],
                        })
                      }
                    />
                    {l.label}
                  </label>
                ))}
                {lanes.length === 0 && (
                  <span>Run a classifier to add a signal lane.</span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="timeline-scroll">
        {data && <AgentLanes markers={data.markers} total={total} />}
        <div className="phase-lane">
          <span className="timeline-lane-label">Phases</span>
          <div className="phase-track">
            {data?.segments
              .filter((s) => !s.parentId)
              .map((s, i) => (
                <button
                  className={`phase-block phase-block-${i % 4}`}
                  style={{
                    left: `${(s.startEvent / total) * 100}%`,
                    width: `${((s.endEvent - s.startEvent + 1) / total) * 100}%`,
                  }}
                  key={s.id}
                  title={`${s.label}: #${s.startEvent}–${s.endEvent}`}
                  onClick={() => {
                    ui.jump(s.startEvent)
                    ui.set({
                      range: {
                        start: s.startEvent,
                        end: s.endEvent,
                        label: s.label,
                      },
                    })
                  }}
                >
                  {s.label}
                </button>
              ))}
          </div>
        </div>
        <div className="timeline-chart-wrap" style={{ height }}>
          <div className="timeline-labels">
            <span>Tools & errors</span>
            {visible.map((l, i) => (
              <span key={l.id}>
                <i style={{ background: palette[i % palette.length] }} />
                {l.label}
              </span>
            ))}
          </div>
          <div className="timeline-chart" style={{ height }} ref={ref} />
        </div>
        {data?.annotations.length ||
        data?.forks.length ||
        data?.checkpoints.length ? (
          <div className="annotation-lane">
            <span className="timeline-lane-label">Notes & branches</span>
            <div className="phase-track">
              {data.annotations.map((a) => (
                <button
                  key={a.id}
                  className="annotation-tick"
                  style={{ left: `${(a.startEventIndex / total) * 100}%` }}
                  title={a.label}
                  onClick={() => ui.jump(a.startEventIndex)}
                >
                  ⚑
                </button>
              ))}
              {data.forks.map((f) => (
                <button
                  key={f.id}
                  className="annotation-tick"
                  style={{
                    left: `${(Number(f.metadata.sourceEventIndex || 0) / total) * 100}%`,
                  }}
                  title="Fork point"
                  onClick={() => ui.set({ section: 'forks' })}
                >
                  ⑂
                </button>
              ))}
              {data.checkpoints.map((c) => (
                <button
                  key={c.id}
                  className="annotation-tick"
                  style={{ left: `${(c.index / total) * 100}%` }}
                  title="Checkpoint marker · restoration unavailable"
                  onClick={() => ui.jump(c.index)}
                >
                  ◇
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
