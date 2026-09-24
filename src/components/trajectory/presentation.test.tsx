// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { rpc } from '@/lib/api'
import { useUI } from '@/stores/ui'
import { TrajectoryView } from './TrajectoryView'
import { EventInspector } from './EventInspector'
import { activities } from '@/features/analysis/coordinates'
import type { CoordinatePoint } from '@/types/analysis'

const scroll = vi.hoisted(() => vi.fn())
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: () => ({
    getVirtualItems: () => [{ index: 0, start: 0, size: 87 }],
    getTotalSize: () => 87,
    measure: () => {},
    scrollToIndex: scroll,
  }),
}))
vi.mock('@/lib/api', () => ({ rpc: vi.fn(), openNative: vi.fn() }))
vi.mock('@/hooks/queries', () => ({
  useTrajectory: () => ({
    data: {
      trajectory: {
        id: 't',
        sampleId: 's',
        eventCount: 101,
        metadata: {},
        status: 'success',
      },
      eventCounts: {
        recorded: 101,
        research: 100,
        runtime: 1,
        opaque: 1,
        semantic: 99,
      },
      capabilities: { contextOnly: false },
    },
  }),
  useTimeline: () => ({
    data: { segments: [], annotations: [], results: [], forks: [] },
  }),
  useClassifiers: () => ({ data: [] }),
}))
vi.mock('@/features/sources/SourcePanel', () => ({ SourceBadge: () => null }))
vi.mock('@/features/analysis/SignalInspector', () => ({
  AnalysisStack: () => null,
}))
vi.mock('./EventRelations', () => ({ EventRelations: () => null }))
const call = vi.mocked(rpc)
const payload = 'ciphertext-not-human-readable'
const event = {
  id: 't:e70',
  trajectoryId: 't',
  index: 70,
  type: 'reasoning',
  content: null,
  parentEventIds: [],
  metadata: { presentationClass: 'opaque', reasoningVisibility: 'redacted' },
}
afterEach(cleanup)
beforeEach(() => {
  useUI.persist.setOptions({
    storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  })
  scroll.mockReset()
  call.mockReset()
  useUI.setState({
    trajectoryId: 't',
    selectedIndex: 70,
    mode: 'reasoning',
    range: null,
    jumpVersion: 0,
  })
  call.mockImplementation(async (method, params) => {
    if (method === 'events.locate')
      return { offset: 0, exact: true, eventIndex: 70 }
    if (method === 'events.get') return { event, results: [] }
    if (method === 'events.raw')
      return { contentBlock: { reasoning: payload, redacted: true } }
    if (method === 'events.list') {
      const runtime = (params as { mode: string }).mode === 'runtime'
      return {
        total: 1,
        items: [
          runtime
            ? {
                id: 't:e0',
                index: 0,
                type: 'other',
                preview: 'span_begin',
                presentationClass: 'runtime',
              }
            : {
                ...event,
                preview: '',
                presentationClass: 'opaque',
                reasoningVisibility: 'redacted',
              },
        ],
      }
    }
    throw Error(method)
  })
})
function mount(content: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {content}
    </QueryClientProvider>,
  )
}
it('Reasoning mode renders a compact placeholder; Runtime reveals preserved records', async () => {
  mount(<TrajectoryView />)
  await screen.findByText('Redacted reasoning')
  expect(
    screen.getByText('Provider reasoning state is preserved but not readable.'),
  ).toBeTruthy()
  expect(screen.queryByText(payload)).toBeNull()
  expect(screen.queryByText('span_begin')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Runtime' }))
  await screen.findByText('span_begin')
  expect(useUI.getState().selectedIndex).toBe(70)
  fireEvent.click(screen.getByRole('button', { name: 'All events' }))
  await screen.findByText('Redacted reasoning')
  await waitFor(() => expect(scroll).toHaveBeenCalled())
  const count = scroll.mock.calls.length
  fireEvent.click(screen.getByText('Redacted reasoning'))
  await act(async () => {})
  expect(scroll).toHaveBeenCalledTimes(count)
})
it('inspector qualifies opaque reasoning and retrieves the payload only on explicit raw inspection', async () => {
  mount(<EventInspector />)
  await screen.findByRole('heading', { name: 'Redacted reasoning' })
  expect(call.mock.calls.some(([method]) => method === 'events.raw')).toBe(
    false,
  )
  expect(screen.queryByText(new RegExp(payload))).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Show raw payload' }))
  await screen.findByText(new RegExp(payload))
  expect(call).toHaveBeenCalledWith('events.raw', { id: 't:e70' })
})
it('activity lanes separate runtime and opaque reasoning without losing generation boundaries', () => {
  const point = {
    type: 'reasoning',
    presentationClass: 'opaque',
    modelCallBoundary: true,
  } as CoordinatePoint
  expect(activities(point)).toEqual(['Opaque reasoning', 'Model calls'])
  expect(activities({ ...point, presentationClass: 'runtime' })).toEqual([
    'Runtime',
  ])
  expect(activities({ ...point, presentationClass: 'semantic' })).toEqual([
    'Reasoning',
    'Model calls',
  ])
})

it('raw disclosure does not carry over to a newly selected event', async () => {
  mount(<EventInspector />)
  await screen.findByRole('button', { name: 'Show raw payload' })
  fireEvent.click(screen.getByRole('button', { name: 'Show raw payload' }))
  await screen.findByText(new RegExp(payload))
  const previous = call.getMockImplementation()!
  call.mockImplementation(async (method, params) =>
    method === 'events.get'
      ? { event: { ...event, id: 't:e76', index: 76 }, results: [] }
      : previous(method, params),
  )
  act(() => useUI.getState().select(76))
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith('events.get', {
      trajectoryId: 't',
      index: 76,
    }),
  )
  await act(async () => {})
  expect(call).not.toHaveBeenCalledWith('events.raw', { id: 't:e76' })
})
