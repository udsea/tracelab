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
import { ForkForm } from './ForkLab'

vi.mock('@/lib/api', () => ({ rpc: vi.fn(), openNative: vi.fn() }))
const call = vi.mocked(rpc)

beforeEach(() => {
  useUI.persist.setOptions({
    storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  })
  call.mockReset()
  call.mockImplementation(async (method, params) => {
    if (method === 'trajectories.get')
      return {
        trajectory: {
          id: 't',
          sampleId: '83',
          model: 'example/agent',
          metadata: {},
        },
        eventCounts: {},
        capabilities: {
          contextOnly: true,
          checkpointRestored: false,
          reason: '',
        },
      }
    if (method === 'providers.list') return []
    if (method === 'events.get') {
      const { index } = params as { index: number }
      return {
        event: {
          id: `t:e${index}`,
          trajectoryId: 't',
          index,
          type: 'reasoning',
          content: `original reasoning at ${index}`,
          parentEventIds: [],
          metadata: {},
        },
        results: [],
      }
    }
    if (method === 'forks.run') return { id: 'job' }
    if (method === 'forks.preview')
      return {
        sourceEventIndex: 214,
        model: 'm',
        provider: {
          id: 'openai',
          name: 'OpenAI',
          kind: 'openai_compatible',
          baseUrl: 'u',
          apiKeyEnv: 'OPENAI_API_KEY',
        },
        parameters: { max_tokens: 2048 },
        seedIncrementsByReplication: false,
        replicationCount: 1,
        messages: [],
        inputHash: 'abc',
        contextCharacters: 400,
        replaySupport: { supported: true, reasonCode: null, reason: 'Ready' },
        toolCatalog: { count: 1, hash: 'catalog', names: ['read_file'] },
        replayPlan: {
          policy: 'strict_sequential_exact_v1',
          entryCount: 2,
          hash: 'plan',
          entries: [],
        },
      }
    throw Error(method)
  })
})
afterEach(cleanup)

it('targets the selected event and preloads its original content', async () => {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ForkForm trajectoryId="t" selectedIndex={214} />
    </QueryClientProvider>,
  )
  expect(await screen.findByText(/Event #214/)).toBeTruthy()
  // No manual index entry is needed; the target input only appears on request.
  expect(screen.queryByLabelText('Target event index')).toBeNull()
  const original = await screen.findByTestId('original-content')
  expect(original.textContent).toBe('original reasoning at 214')
  const replacement = screen.getByLabelText(
    /Replacement/,
  ) as HTMLTextAreaElement
  expect(replacement.value).toBe('original reasoning at 214')
  // Fidelity detail is behind the compact badge, not always expanded.
  expect(
    screen
      .getByRole('button', { name: /CONTEXT-ONLY/ })
      .getAttribute('aria-expanded'),
  ).toBe('false')
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith(
      'forks.preview',
      expect.objectContaining({
        sourceEventId: 't:e214',
        interventions: [
          {
            type: 'replace_content',
            eventId: 't:e214',
            content: 'original reasoning at 214',
          },
        ],
        modelOverrides: expect.objectContaining({
          parameters: { max_tokens: 2048 },
        }),
      }),
    ),
  )
  expect(await screen.findByText(/≈100 context tokens/)).toBeTruthy()
  expect(screen.getByText(/Monetary cost unavailable/)).toBeTruthy()
})

it('sends the same replay specification to preview and run and blocks unsupported plans', async () => {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ForkForm trajectoryId="t" selectedIndex={214} />
    </QueryClientProvider>,
  )
  await screen.findByTestId('original-content')
  fireEvent.change(screen.getByLabelText('Continuation mode'), {
    target: { value: 'multi_step' },
  })
  fireEvent.change(screen.getByLabelText('Continuation model'), {
    target: { value: 'test-model' },
  })
  fireEvent.change(screen.getByLabelText('Max model steps'), {
    target: { value: '3' },
  })
  await screen.findByText(/2 sequential recorded observations/)
  await waitFor(() =>
    expect(
      (screen.getByRole('button', { name: 'Run fork' }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Run fork' }))
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith(
      'forks.run',
      expect.objectContaining({
        executionSpec: expect.objectContaining({
          continuation: 'multi_step',
          toolPolicy: 'recorded_replay',
          maxModelSteps: 3,
          environment: 'none',
          scoring: 'none',
        }),
      }),
    ),
  )
  const run = call.mock.calls.find((c) => c[0] === 'forks.run')![1]
  expect(call).toHaveBeenCalledWith('forks.preview', run)
  const original = call.getMockImplementation()!
  call.mockImplementation(async (method, params) =>
    method === 'forks.preview'
      ? {
          ...((await original(method, params)) as object),
          replaySupport: {
            supported: false,
            reasonCode: 'tool_schema_unavailable',
            reason: 'No schemas',
          },
        }
      : original(method, params),
  )
  fireEvent.change(screen.getByLabelText('Max model steps'), {
    target: { value: '4' },
  })
  await screen.findByText(/tool_schema_unavailable/)
  expect(
    (screen.getByRole('button', { name: 'Run fork' }) as HTMLButtonElement)
      .disabled,
  ).toBe(true)
})
