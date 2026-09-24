// @vitest-environment jsdom
import {
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
import { ExperimentBuilder, trialTotal } from './ExperimentBuilder'
import { ExperimentDetail } from './ExperimentDetail'
vi.mock('@/lib/api', () => ({ rpc: vi.fn() }))
const call = vi.mocked(rpc)
const cases = ['A', 'B'].map((id, index) => ({
  id,
  sourceTrajectoryId: id,
  sourceEventId: `${id}:fork-${index}`,
  arms: [
    { armId: 'control', interventions: [] },
    {
      armId: 'treatment',
      interventions: [{ type: 'remove_event', eventId: `${id}:hint-${index}` }],
    },
  ],
}))
let supported = true
let status = 'running'
let pending = 2
beforeEach(() => {
  supported = true
  status = 'running'
  pending = 2
  useUI.persist.setOptions({
    storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  })
  useUI.setState({ workspaceId: 'ws', trajectoryId: 'A', selectedIndex: 7 })
  call.mockReset()
  call.mockImplementation(async (method) => {
    if (method === 'providers.list') return []
    if (method === 'events.get')
      return { event: { id: 'actual-record-id', trajectoryId: 'A' } }
    if (method === 'forkExperiments.preview')
      return {
        specHash: 'hash',
        allSupported: supported,
        totalTrials: 12,
        cells: cases.flatMap((c) =>
          c.arms.map((a) => ({
            caseId: c.id,
            armId: a.armId,
            supported,
            reasonCode: supported ? undefined : 'tool_schema_unavailable',
            reason: 'No recorded schemas',
          })),
        ),
      }
    if (method === 'forkExperiments.run' || method === 'forkExperiments.resume')
      return { started: true, experimentId: 'fe', job: { id: 'job' } }
    if (method === 'jobs.cancel') return { requested: true }
    if (method === 'forkExperiments.get')
      return {
        experiment: {
          id: 'fe',
          name: 'Study',
          status,
          jobId: 'job',
          arms: [
            { id: 'control', name: 'Control', role: 'control' },
            { id: 'treatment', name: 'Treatment', role: 'treatment' },
          ],
          cases,
        },
        progress: {
          finalized: 2,
          total: 4,
          complete: 1,
          error: 1,
          pending,
          interrupted: 0,
          cancelled: 0,
        },
        cells: cases.flatMap((c) =>
          c.arms.map((a) => ({
            caseId: c.id,
            armId: a.armId,
            progress: { complete: 1, total: 3, error: 1 },
            terminationCounts: {},
          })),
        ),
        usage: {},
        trials: [],
      }
    if (method === 'forkExperiments.trials')
      return [
        {
          id: 'trial',
          caseId: 'A',
          armId: 'control',
          replicationIndex: 0,
          childTrajectoryId: 'child',
          status: 'complete',
          pairKey: 'A:r0',
          requestedSeed: 50,
          scheduleOrdinal: 0,
          metadata: { terminationReason: 'assistant_completed' },
        },
      ]
    throw Error(method)
  })
})
afterEach(cleanup)
function mount(element: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      {element}
    </QueryClientProvider>,
  )
}
function fill() {
  fireEvent.change(screen.getByLabelText('Concrete source cases (JSON)'), {
    target: { value: JSON.stringify(cases) },
  })
  fireEvent.change(screen.getByLabelText('Model'), {
    target: { value: 'local-model' },
  })
  fireEvent.change(screen.getByLabelText('Replications'), {
    target: { value: '3' },
  })
}
it('computes totals and submits concrete distinct bindings with reviewed hash', async () => {
  expect(trialTotal(2, 2, 3)).toBe(12)
  const started = vi.fn()
  mount(<ExperimentBuilder workspaceId="ws" onStarted={started} />)
  fill()
  expect(screen.getByText('12 trials')).toBeTruthy()
  expect(
    (screen.getByText('Run experiment') as HTMLButtonElement).disabled,
  ).toBe(true)
  fireEvent.click(screen.getByText('Validate all cells'))
  await waitFor(() =>
    expect(
      (screen.getByText('Run experiment') as HTMLButtonElement).disabled,
    ).toBe(false),
  )
  fireEvent.click(screen.getByText('Run experiment'))
  await waitFor(() => expect(started).toHaveBeenCalledWith('fe'))
  const request = call.mock.calls.find(
    ([m]) => m === 'forkExperiments.run',
  )?.[1] as Record<string, unknown>
  expect(request.cases).toEqual(cases)
  expect(request.expectedSpecHash).toBe('hash')
})
it('blocks unsupported cells and invalidates preview when design changes', async () => {
  supported = false
  mount(<ExperimentBuilder workspaceId="ws" onStarted={() => {}} />)
  fill()
  fireEvent.click(screen.getByText('Validate all cells'))
  await screen.findByText('0 / 4 case-arm cells supported')
  expect(
    (screen.getByText('Run experiment') as HTMLButtonElement).disabled,
  ).toBe(true)
  supported = true
  fireEvent.click(screen.getByText('Validate all cells'))
  await screen.findByText('4 / 4 case-arm cells supported')
  fireEvent.change(screen.getByLabelText('Replications'), {
    target: { value: '4' },
  })
  expect(
    (screen.getByText('Run experiment') as HTMLButtonElement).disabled,
  ).toBe(true)
})
it('adds the selected concrete event using its real ID, with empty control interventions', async () => {
  mount(<ExperimentBuilder workspaceId="ws" onStarted={() => {}} />)
  fireEvent.click(screen.getByText('Add selected event as a case'))
  await waitFor(() =>
    expect(
      (
        screen.getByLabelText(
          'Concrete source cases (JSON)',
        ) as HTMLTextAreaElement
      ).value,
    ).toContain('actual-record-id'),
  )
  const parsed = JSON.parse(
    (
      screen.getByLabelText(
        'Concrete source cases (JSON)',
      ) as HTMLTextAreaElement
    ).value,
  )
  expect(parsed[0].sourceEventId).toBe('actual-record-id')
  expect(parsed[0].arms[0].interventions).toEqual([])
})
it('renders matrix, progress and pairing; opens child and uses jobs.cancel', async () => {
  mount(<ExperimentDetail id="fe" />)
  await screen.findByRole('table', { name: 'Experiment trial matrix' })
  expect(screen.getAllByText('1/3 complete · 1 errors')).toHaveLength(4)
  expect(screen.getByText(/2 \/ 4 finalized/)).toBeTruthy()
  fireEvent.click(await screen.findByText('A / control · replicate 1'))
  expect(useUI.getState().trajectoryId).toBe('child')
  fireEvent.click(screen.getByText('Cancel experiment'))
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith('jobs.cancel', { id: 'job' }),
  )
  expect(screen.queryByText('Resume pending trials')).toBeNull()
})
it.each([
  ['partial', 1, true],
  ['cancelled', 1, true],
  ['partial', 0, false],
  ['complete', 0, false],
])('resume visibility %s pending %s', async (state, count, visible) => {
  status = String(state)
  pending = Number(count)
  mount(<ExperimentDetail id="fe" />)
  await screen.findByText('Study')
  expect(!!screen.queryByText('Resume pending trials')).toBe(visible)
  if (visible) {
    fireEvent.click(screen.getByText('Resume pending trials'))
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith('forkExperiments.resume', { id: 'fe' }),
    )
  }
})
