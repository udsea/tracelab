// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import {
  defaultExecution,
  ExecutionOptions,
  ExecutionSummary,
  parseStubs,
  ReplaySummary,
  ToolOrigin,
} from './ExecutionOptions'
import { useUI } from '@/stores/ui'
afterEach(cleanup)
it('defaults to one reply and serializes only supported replay mode', () => {
  const onChange = vi.fn()
  render(
    <ExecutionOptions
      value={defaultExecution}
      onChange={onChange}
      stubs="[]"
      onStubs={() => {}}
    />,
  )
  expect(
    (screen.getByLabelText('Continuation mode') as HTMLSelectElement).value,
  ).toBe('single_turn')
  expect(screen.queryByLabelText('Max model steps')).toBeNull()
  fireEvent.change(screen.getByLabelText('Continuation mode'), {
    target: { value: 'multi_step' },
  })
  expect(onChange).toHaveBeenCalledWith({
    ...defaultExecution,
    continuation: 'multi_step',
    toolPolicy: 'recorded_replay',
  })
})
it('exposes bounds, exact stub policy and honest wording', () => {
  const value = {
    ...defaultExecution,
    continuation: 'multi_step' as const,
    toolPolicy: 'recorded_replay' as const,
    unmatchedToolPolicy: 'stub' as const,
  }
  const onChange = vi.fn(),
    onStubs = vi.fn()
  render(
    <ExecutionOptions
      value={value}
      onChange={onChange}
      stubs="[]"
      onStubs={onStubs}
    />,
  )
  expect(
    screen.getByText(
      /Tools are not executed and environment state is not restored/,
    ),
  ).toBeTruthy()
  expect(screen.getByText(/recorded replay cannot resume/)).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Max model steps'), {
    target: { value: '3' },
  })
  expect(onChange).toHaveBeenCalledWith({ ...value, maxModelSteps: 3 })
  fireEvent.change(screen.getByLabelText('Max tool calls'), {
    target: { value: '9' },
  })
  expect(onChange).toHaveBeenCalledWith({ ...value, maxToolCalls: 9 })
  fireEvent.change(screen.getByLabelText('Exact stubs'), {
    target: { value: '[{"id":"s"}]' },
  })
  expect(onStubs).toHaveBeenCalledWith('[{"id":"s"}]')
  expect(parseStubs('[{"id":"s"}]').error).toBeTruthy()
  expect(
    parseStubs('[{"id":"s","toolName":"a","arguments":{},"result":"x"}]').stubs,
  ).toHaveLength(1)
})
it('renders plan and fail-closed capability explanation without result bodies', () => {
  render(
    <ReplaySummary
      preview={{
        replaySupport: {
          supported: false,
          reasonCode: 'tool_schema_unavailable',
          reason: 'No explicit schemas',
        },
        toolCatalog: null,
        replayPlan: {
          policy: 'strict_sequential_exact_v1',
          entryCount: 0,
          hash: null,
          entries: [],
        },
      }}
    />,
  )
  expect(screen.getByText(/tool_schema_unavailable/)).toBeTruthy()
  expect(screen.getByText(/0 sequential recorded observations/)).toBeTruthy()
})
it('distinguishes recorded and synthetic results and links recorded evidence', () => {
  useUI.persist.setOptions({
    storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  })
  const { rerender } = render(
    <ToolOrigin
      metadata={{
        toolResultOrigin: 'recorded_replay',
        matchedSourceTrajectoryId: 'parent',
        matchedSourceCallIndex: 12,
        matchedSourceResultIndex: 14,
        matchPolicy: 'strict_sequential_exact_v1',
      }}
    />,
  )
  expect(screen.getByText('RECORDED REPLAY')).toBeTruthy()
  fireEvent.click(screen.getByText('Source result #14'))
  expect(useUI.getState().trajectoryId).toBe('parent')
  expect(useUI.getState().selectedIndex).toBe(14)
  rerender(<ToolOrigin metadata={{ toolResultOrigin: 'stub', stubId: 's' }} />)
  expect(screen.getByText('STUBBED')).toBeTruthy()
  expect(screen.getByText(/Researcher-supplied synthetic result/)).toBeTruthy()
  expect(screen.queryByText(/Source result/)).toBeNull()
  rerender(<ToolOrigin metadata={{}} />)
  expect(screen.queryByText('STUBBED')).toBeNull()
})
it('shows branch termination independently of task outcome', () => {
  render(
    <ExecutionSummary
      metadata={{
        executionMode: 'multi_step_recorded_replay',
        modelSteps: 3,
        replayedToolCalls: 2,
        stubbedToolCalls: 1,
        terminationReason: 'unmatched_tool_call',
        replayState: 'diverged_by_stub',
      }}
    />,
  )
  expect(
    screen.getByText(/3 model calls · 2 replayed · 1 stubbed/),
  ).toBeTruthy()
  expect(screen.getByText(/Stopped at unmatched tool call/)).toBeTruthy()
  expect(screen.getByText(/Replay diverged after stub/)).toBeTruthy()
})
