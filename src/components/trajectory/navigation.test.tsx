// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { rpc } from '@/lib/api'
import { useEventNavigation } from './useEventNavigation'
import type { EventLocation } from '@/types/domain'
vi.mock('@/lib/api', () => ({ rpc: vi.fn() }))
const call = vi.mocked(rpc)
afterEach(cleanup)
beforeEach(() => {
  call.mockReset()
})
const located = (offset: number, exact = true): EventLocation => ({
  offset,
  exact,
  eventIndex: 70,
  nearestEventIndex: exact ? null : 80,
})

describe('canonical selection versus virtual row navigation', () => {
  it('locates #70 in Reasoning then All; row clicks and refetches do not hijack scroll', async () => {
    call.mockImplementation(async (_method, params) =>
      located((params as { mode: string }).mode === 'reasoning' ? 11 : 69),
    )
    const scroll = vi.fn()
    const { rerender } = renderHook(
      ({ mode, selected, total, jump }) =>
        useEventNavigation(
          { trajectoryId: 't', mode },
          selected,
          jump,
          total,
          scroll,
        ),
      {
        initialProps: { mode: 'reasoning', selected: 70, total: 17, jump: 0 },
      },
    )
    await waitFor(() => expect(scroll).toHaveBeenLastCalledWith(11))
    rerender({ mode: 'all', selected: 70, total: 100, jump: 0 })
    await waitFor(() => expect(scroll).toHaveBeenLastCalledWith(69))
    expect(scroll).not.toHaveBeenCalledWith(70)
    expect(scroll).not.toHaveBeenCalledWith(0)
    const calls = scroll.mock.calls.length
    rerender({ mode: 'all', selected: 75, total: 100, jump: 0 })
    rerender({ mode: 'all', selected: 75, total: 101, jump: 0 })
    await act(async () => {})
    expect(scroll).toHaveBeenCalledTimes(calls)
    rerender({ mode: 'all', selected: 75, total: 101, jump: 1 })
    await waitFor(() => expect(scroll).toHaveBeenCalledTimes(calls + 1))
    expect(call).toHaveBeenLastCalledWith('events.locate', {
      trajectoryId: 't',
      mode: 'all',
      eventIndex: 75,
    })
  })

  it('uses nearest filtered row without overwriting the canonical selection', async () => {
    call.mockResolvedValue(located(0, false))
    const scroll = vi.fn()
    const { result } = renderHook(() =>
      useEventNavigation(
        { trajectoryId: 't', mode: 'tools', start: 60, end: 90, query: 'bash' },
        70,
        0,
        1,
        scroll,
      ),
    )
    await waitFor(() => expect(scroll).toHaveBeenCalledWith(0))
    expect(result.current?.location).toEqual(located(0, false))
    expect(call).toHaveBeenCalledWith('events.locate', {
      trajectoryId: 't',
      mode: 'tools',
      start: 60,
      end: 90,
      query: 'bash',
      eventIndex: 70,
    })
  })

  it('ignores stale filter requests, including a rapid return to the previous mode', async () => {
    const pending: ((value: EventLocation) => void)[] = []
    call.mockImplementation(
      () => new Promise((resolve) => pending.push(resolve)),
    )
    const scroll = vi.fn()
    const { rerender } = renderHook(
      ({ mode }) =>
        useEventNavigation({ trajectoryId: 't', mode }, 70, 0, 100, scroll),
      { initialProps: { mode: 'all' } },
    )
    await act(async () => pending[0](located(69)))
    rerender({ mode: 'reasoning' })
    rerender({ mode: 'all' })
    await act(async () => pending[1](located(11)))
    expect(scroll).toHaveBeenCalledTimes(1)
    await act(async () => pending[2](located(69)))
    expect(scroll).toHaveBeenCalledTimes(2)
    expect(scroll).toHaveBeenLastCalledWith(69)
  })

  it('waits for rows and does not navigate after a row click', async () => {
    const scroll = vi.fn()
    let resolve!: (value: EventLocation) => void
    call.mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    const { rerender } = renderHook(
      ({ total, selected }) =>
        useEventNavigation(
          { trajectoryId: 't', mode: 'all' },
          selected,
          0,
          total,
          scroll,
        ),
      {
        initialProps: { total: undefined as number | undefined, selected: 70 },
      },
    )
    expect(call).not.toHaveBeenCalled()
    rerender({ total: 101, selected: 70 })
    rerender({ total: 101, selected: 71 })
    await act(async () => resolve(located(69)))
    expect(scroll).not.toHaveBeenCalled()
  })
})

it('initial opening selects the first research event; an explicit later jump retains runtime selection', async () => {
  call.mockResolvedValue({
    offset: 0,
    exact: false,
    eventIndex: 0,
    nearestEventIndex: 2,
  })
  const select = vi.fn(),
    scroll = vi.fn()
  const { rerender } = renderHook(
    ({ jump }) =>
      useEventNavigation(
        { trajectoryId: 't', mode: 'all' },
        0,
        jump,
        100,
        scroll,
        select,
      ),
    { initialProps: { jump: 0 } },
  )
  await waitFor(() => expect(select).toHaveBeenCalledWith(2))
  rerender({ jump: 1 })
  await waitFor(() => expect(scroll).toHaveBeenCalledTimes(2))
  expect(select).toHaveBeenCalledTimes(1)
})

it('an empty filtered view has no virtual row to scroll to', async () => {
  call.mockResolvedValue({
    offset: null,
    exact: false,
    eventIndex: 70,
    nearestEventIndex: null,
  })
  const scroll = vi.fn()
  const { result } = renderHook(() =>
    useEventNavigation({ trajectoryId: 't', mode: 'errors' }, 70, 0, 0, scroll),
  )
  await waitFor(() => expect(result.current?.location?.offset).toBeNull())
  expect(scroll).not.toHaveBeenCalled()
})
