import type { CoordinatePoint } from '@/types/analysis'
export type Scale = 'events' | 'time' | 'calls'
export function coordinateMap(points: CoordinatePoint[], scale: Scale) {
  const known = points.filter((p) => p.elapsedMs !== null)
  const maxTime = known.reduce((max, p) => Math.max(max, p.elapsedMs!), 0)
  // Missing timestamps occupy an explicitly labeled ordinal gutter, never invented time.
  const unknown = points.filter((p) => p.elapsedMs === null)
  const gutterWidth = Math.max(maxTime * 0.1, 1)
  const missing = new Map(
    unknown.map((p, i) => [
      p.index,
      maxTime + (gutterWidth * (i + 1)) / Math.max(1, unknown.length),
    ]),
  )
  const values = new Map(
    points.map((p) => [
      p.index,
      scale === 'events'
        ? p.index
        : scale === 'calls'
          ? p.modelCall
          : (p.elapsedMs ?? missing.get(p.index)!),
    ]),
  )
  const max = points.reduce(
    (max, p) => Math.max(max, values.get(p.index) ?? 0),
    1,
  )
  return {
    values,
    max,
    maxTime,
    hasGutter: scale === 'time' && unknown.length > 0,
    at: (index: number) => values.get(index) ?? 0,
    extent: (start: number, end: number): [number, number] => {
      const selected = points.filter((p) => p.index >= start && p.index <= end)
      return selected.reduce<[number, number]>(
        (bounds, p) => {
          const value = values.get(p.index) ?? 0
          return [Math.min(bounds[0], value), Math.max(bounds[1], value)]
        },
        selected.length ? [Infinity, -Infinity] : [0, max],
      )
    },
    nearest: (x: number) =>
      points.reduce(
        (best, p) =>
          Math.abs((values.get(p.index) ?? 0) - x) <
          Math.abs((values.get(best) ?? 0) - x)
            ? p.index
            : best,
        points[0]?.index ?? 0,
      ),
  }
}
export function activities(p: CoordinatePoint): string[] {
  if (p.presentationClass === 'runtime') return ['Runtime']
  const base =
    p.presentationClass === 'opaque'
      ? 'Opaque reasoning'
      : ((
          {
            reasoning: 'Reasoning',
            tool_call: 'Tool calls',
            tool_result: 'Tool results',
            environment: 'Environment',
            score: 'Scores',
            checkpoint: 'Checkpoints',
            system: 'Messages',
            user: 'Messages',
            assistant: 'Messages',
            error: 'Errors',
          } as Record<string, string>
        )[p.type] ?? 'Other')
  return [
    ...new Set([
      base,
      ...(p.error ? ['Errors'] : []),
      ...(p.modelCallBoundary ? ['Model calls'] : []),
      ...(p.artifacts ? ['Artifacts'] : []),
    ]),
  ]
}
