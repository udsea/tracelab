// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { rpc } from '@/lib/api'
import { useUI } from '@/stores/ui'
import type { AnalysisSignal } from '@/types/analysis'
import { AnalysisWorkspace, analysisNavigation } from './AnalysisWorkspace'
import { AnalysisStack, coveringSignals } from './SignalInspector'

vi.mock('@/lib/api', () => ({ rpc: vi.fn(), openNative: vi.fn() }))
vi.mock('@/features/classifiers/ClassifierWorkspace', () => ({
  ClassifierWorkspace: () => <div>semantic detector editor</div>,
}))
vi.mock('./DetectorEditor', () => ({
  DetectorEditor: ({ kind }: { kind: string }) => <div>{kind} detector editor</div>,
}))
vi.mock('./ArtifactImport', () => ({ ArtifactImport: () => null }))
vi.mock('./ExecutionGraph', () => ({ ExecutionGraph: () => null }))
vi.mock('./ContrastiveSignals', () => ({ ContrastiveSignals: () => null }))
vi.mock('@/components/trajectory/TrajectoryPicker', () => ({
  TrajectoryPicker: () => null,
}))

const call = vi.mocked(rpc)
const signal = (over: Partial<AnalysisSignal>): AnalysisSignal => ({
  id: 's',
  trajectoryId: 't',
  name: 'Evaluation awareness',
  sourceType: 'llm',
  channel: 'BLACK_BOX',
  startEventIndex: 0,
  endEventIndex: 9,
  score: 0.1,
  label: null,
  evidenceEventIds: [],
  artifactRef: null,
  provenance: { detectorId: 'awareness' },
  metadata: { laneId: 'awareness' },
  ...over,
})
let signals: AnalysisSignal[] = []

beforeEach(() => {
  useUI.persist.setOptions({
    storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  })
  useUI.setState({
    workspaceId: 'w',
    trajectoryId: 't',
    selectedIndex: 5,
    section: 'classifiers',
    analysisTab: 'overview',
  })
  signals = [0.1, 0.1, 0.2, 0.7, 0.9].map((score, i) =>
    signal({ id: `w${i}`, score, startEventIndex: i * 10, endEventIndex: i * 10 + 9 }),
  )
  call.mockReset()
  call.mockImplementation(async (method) => {
    if (method === 'analysis.signals') return signals
    if (method === 'analysis.overview')
      return {
        eventCounts: { recorded: 50, research: 50, runtime: 0, opaque: 0, semantic: 50 },
        coordinates: { points: [], missingTimestamps: 0, modelCallFidelity: '' },
        outline: [],
        relationships: [],
        analysisCapabilities: {},
        artifacts: [],
      }
    if (method === 'timeline')
      return { segments: [], annotations: [], results: [], forks: [] }
    if (method === 'trajectories.list') return { items: [], total: 0 }
    if (method === 'analysis.matchCandidates') return []
    throw Error(method)
  })
})
afterEach(cleanup)

function mount(node: ReactNode) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {node}
    </QueryClientProvider>,
  )
}

describe('analysis information architecture', () => {
  it('groups analysis into five top-level sections with secondary navigation', () => {
    expect(analysisNavigation.map((g) => g.label)).toEqual([
      'Overview',
      'Signals',
      'Compare',
      'Internals',
      'Notes',
    ])
    mount(<AnalysisWorkspace />)
    const nav = screen.getByRole('navigation', { name: 'Analysis sections' })
    expect(within(nav).getAllByRole('button')).toHaveLength(5)
    fireEvent.click(within(nav).getByText('Signals'))
    const sub = screen.getByRole('navigation', { name: 'Signals sections' })
    expect(within(sub).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Semantic / LLM',
      'Rules',
      'Statistical',
      'Environment',
    ])
    expect(screen.getByText('semantic detector editor')).toBeTruthy()
    fireEvent.click(within(sub).getByText('Rules'))
    expect(screen.getByText('rule detector editor')).toBeTruthy()
  })

  it('leads with a summary and keeps the raw measurement list behind a toggle', async () => {
    mount(<AnalysisWorkspace />)
    expect(await screen.findByText(/rises around #30–39/)).toBeTruthy()
    expect(document.querySelector('.signal-summary-list')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Show all measurements \(5\)/ }))
    expect(document.querySelector('.signal-summary-list')).toBeTruthy()
  })
})

describe('inspector analysis stack', () => {
  it('shows one compact empty state instead of empty channel sections', async () => {
    signals = []
    mount(<AnalysisStack />)
    expect(await screen.findByText('No analysis signals cover this event.')).toBeTruthy()
    expect(screen.queryByText('Gray box')).toBeNull()
    expect(screen.queryByText('White box')).toBeNull()
  })

  it('lists only channels with measurements and explains channels on request', async () => {
    mount(<AnalysisStack />)
    expect(await screen.findByText('Black box')).toBeTruthy()
    expect(screen.queryByText('Gray box')).toBeNull()
    expect(screen.queryByText(/Imported model-internal/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /What are black, gray and white box/ }))
    expect(screen.getByText(/Imported model-internal/)).toBeTruthy()
  })

  it('collapses overlapping windows from one lane', () => {
    const rows = coveringSignals(
      [
        signal({ id: 'a', startEventIndex: 0, endEventIndex: 20 }),
        signal({ id: 'b', startEventIndex: 5, endEventIndex: 15 }),
        signal({ id: 'c', startEventIndex: 30, endEventIndex: 40 }),
      ],
      10,
    )
    expect(rows.map((r) => r.id)).toEqual(['b'])
  })
})
