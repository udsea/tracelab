import { describe, expect, it } from 'vitest'
import type { AnalysisSignal } from '@/types/analysis'
import { deriveRunOverview, downsample, summarizeSeries } from './overview'

const signal = (over: Partial<AnalysisSignal>): AnalysisSignal => ({
  id: Math.random().toString(36).slice(2),
  trajectoryId: 't',
  name: 'Evaluation awareness',
  sourceType: 'llm',
  channel: 'BLACK_BOX',
  startEventIndex: 0,
  endEventIndex: 19,
  score: 0,
  label: null,
  evidenceEventIds: [],
  artifactRef: null,
  provenance: { detectorId: 'awareness' },
  metadata: { laneId: 'awareness' },
  ...over,
})
const rising = [0.1, 0.1, 0.12, 0.2, 0.6, 0.8, 0.85, 0.84].map((score, i) =>
  signal({ id: `w${i}`, score, startEventIndex: i * 20, endEventIndex: i * 20 + 19 }),
)

describe('run overview derivation', () => {
  it('describes a rising series conservatively in its own units', () => {
    const lane = summarizeSeries('Evaluation awareness', rising)
    expect(lane.peak).toMatchObject({ score: 0.85, start: 120 })
    expect(lane.rise).toMatchObject({ start: 80 })
    expect(lane.headline).toBe(
      'Starts near 0.10, rises around #80–99 and peaks at 0.85 (#120–139). Final window 0.84.',
    )
    // No calibration language: nothing is presented as a probability or a conclusion.
    expect(lane.headline).not.toMatch(/%|probab|realis|aware of/i)
    expect(lane.facts).toContainEqual(['First rise', '#80–99'])
  })

  it('does not invent a rise for a flat or noisy series', () => {
    const flat = summarizeSeries(
      'Flat',
      [0.3, 0.3, 0.3].map((score, i) => signal({ score, startEventIndex: i })),
    )
    expect(flat.rise).toBeUndefined()
    expect(flat.headline).toMatch(/^Constant at 0.30/)
  })

  it('collects completed rules without matches separately from families', () => {
    const overview = deriveRunOverview([
      ...rising,
      signal({
        name: 'Evaluator-related access',
        sourceType: 'rule',
        label: 'no_matches',
        score: 0,
        provenance: { detectorId: 'rule-a' },
      }),
      signal({
        name: 'Repeated tool loop',
        sourceType: 'rule',
        label: 'repeated_tool_loop',
        score: 1,
        startEventIndex: 30,
        endEventIndex: 42,
        provenance: { detectorId: 'rule-b' },
        metadata: { laneId: 'rule-b:repeated_tool_loop' },
      }),
    ])
    expect(overview.completedWithoutMatches).toEqual(['Evaluator-related access'])
    expect(overview.families.map((f) => f.name)).toEqual([
      'Evaluation awareness',
      'Repeated tool loop',
    ])
    expect(overview.measured.has('rule')).toBe(true)
    const rule = overview.families[1].lanes[0]
    expect(rule.kind).toBe('matches')
    expect(rule.headline).toBe('1 match at #30–42.')
  })

  it('keeps one moment per lane before letting a busy detector fill the list', () => {
    const loops = Array.from({ length: 12 }, (_, i) =>
      signal({
        name: 'Repeated tool loop',
        sourceType: 'rule',
        label: 'repeated_tool_loop',
        score: 1,
        startEventIndex: i,
        endEventIndex: i,
        provenance: { detectorId: 'loop' },
        metadata: { laneId: 'loop' },
      }),
    )
    const overview = deriveRunOverview([...loops, ...rising])
    const kinds = overview.moments.map((m) => m.label)
    expect(kinds).toContain('Evaluation awareness rises')
    expect(overview.moments.map((m) => m.index)).toEqual(
      [...overview.moments.map((m) => m.index)].sort((a, b) => a - b),
    )
  })

  it('bounds chart data', () => {
    const many = Array.from({ length: 5000 }, (_, i) => ({
      start: i,
      end: i,
      score: i % 7,
      signalId: String(i),
    }))
    expect(downsample(many).length).toBeLessThanOrEqual(120)
  })
})
