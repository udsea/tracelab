import { describe, it, expect } from 'vitest'
import { coordinateMap } from './coordinates'
import type { CoordinatePoint } from '@/types/analysis'
const points = [0, 1, 2].map(
  (i) =>
    ({
      id: String(i),
      index: i,
      elapsedMs: i === 1 ? null : i * 1000,
      modelCall: i === 0 ? 0 : 1,
    }) as CoordinatePoint,
)
describe('coordinate fidelity', () => {
  it('puts missing time into a marked ordinal gutter without mutating timestamps', () => {
    const map = coordinateMap(points, 'time')
    expect(map.hasGutter).toBe(true)
    expect(map.at(1)).toBeGreaterThan(map.maxTime)
    expect(points[1].elapsedMs).toBeNull()
    expect(map.nearest(map.at(1))).toBe(1)
  })
  it('retains deterministic event navigation and grouped model calls', () => {
    expect(coordinateMap(points, 'events').at(2)).toBe(2)
    expect(coordinateMap(points, 'calls').at(1)).toBe(
      coordinateMap(points, 'calls').at(2),
    )
  })
})

describe('large and irregular trajectories', () => {
  it('includes interior untimed events in a range extent', () => {
    const map = coordinateMap(points, 'time')
    expect(map.extent(0, 2)[1]).toBe(map.at(1))
  })
  it('handles large coordinates without spreading into function arguments', () => {
    const many = Array.from({ length: 150000 }, (_, index) => ({
      ...points[0],
      index,
      elapsedMs: index,
    }))
    expect(coordinateMap(many, 'time').max).toBe(149999)
  })
})
