// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { rpc } from '@/lib/api'
import { useUI } from '@/stores/ui'
import { TopBar } from './TopBar'
import { CommandPalette, parseEventQuery } from './CommandPalette'
import { Sidebar } from './Sidebar'

vi.mock('@/lib/api', () => ({ rpc: vi.fn(), openNative: vi.fn() }))
vi.mock('@/features/analysis/RunOutline', () => ({
  RunOutline: () => <div>run outline</div>,
}))
const call = vi.mocked(rpc)

beforeEach(() => {
  useUI.persist.setOptions({
    storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  })
  useUI.setState({
    workspaceId: 'w',
    trajectoryId: 't',
    selectedIndex: 3,
    section: 'trajectory',
    modal: 'commands',
  })
  call.mockReset()
  call.mockImplementation(async (method) => {
    if (method === 'workspaces.list')
      return [
        { id: 'w', name: 'Current', isDemo: false },
        { id: 'w2', name: 'Agent behaviour study', isDemo: true },
      ]
    if (method === 'trajectories.get')
      return {
        trajectory: { id: 't', sampleId: '83', eventCount: 487, metadata: {} },
        eventCounts: {},
        capabilities: { contextOnly: true, checkpointRestored: false, reason: '' },
      }
    if (method === 'trajectories.list')
      return {
        items: [
          { id: 't', sampleId: '83', experimentId: 'e', eventCount: 487, loaded: true, status: 'success', condition: 'baseline', metadata: {} },
          { id: 'c', sampleId: '83 / branch 1', experimentId: 'e', eventCount: 185, loaded: true, status: 'unknown', condition: 'intervention', parentTrajectoryId: 't', metadata: {} },
        ],
        total: 2,
      }
    if (method === 'experiments.list')
      return [{ id: 'e', name: 'baseline', trajectoryCount: 2 }]
    if (method === 'classifiers.list') return []
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

describe('app chrome', () => {
  it('labels search and the command palette with the shortcuts that open them', () => {
    mount(<TopBar />)
    const search = screen.getByRole('button', { name: /Search…/ })
    expect(within(search).getByText('/')).toBeTruthy()
    expect(search.textContent).not.toMatch(/⌘/)
    const commands = screen.getByRole('button', { name: /Commands/ })
    expect(within(commands).getByText('⌘K')).toBeTruthy()
    // Contextual actions are not duplicated in global chrome.
    expect(screen.queryByRole('button', { name: /^Fork/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Analyse/ })).toBeNull()
  })

  it('shows the run outline only in trajectory sections and keeps it mounted', async () => {
    mount(<Sidebar />)
    const slot = await screen.findByTestId('run-outline-slot')
    expect(slot.hidden).toBe(false)
    for (const section of ['forks', 'compare', 'browser'] as const) {
      useUI.setState({ section })
      expect((await screen.findByTestId('run-outline-slot')).hidden).toBe(true)
    }
    useUI.setState({ section: 'classifiers' })
    expect((await screen.findByTestId('run-outline-slot')).hidden).toBe(false)
    expect(await screen.findByText('branch 1')).toBeTruthy()
  })
})

describe('command palette', () => {
  it('parses canonical event addresses', () => {
    expect(parseEventQuery('#214')).toBe(214)
    expect(parseEventQuery('go to 7')).toBe(7)
    expect(parseEventQuery('event #0')).toBe(0)
    expect(parseEventQuery('fork')).toBeNull()
  })

  it('offers navigation commands and jumps to a typed event', async () => {
    mount(<CommandPalette />)
    for (const label of [
      'Open trajectory…',
      'Run detector…',
      'Switch workspace…',
      'Open Analysis',
      'Open Fork Lab',
      'Open Comparisons',
    ])
      expect(screen.getByText(label)).toBeTruthy()
    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: '#214' } })
    expect(await screen.findByText('Go to event #214')).toBeTruthy()
    expect(await screen.findByText(/487 recorded events \(#0–486\)/)).toBeTruthy()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(useUI.getState()).toMatchObject({ selectedIndex: 214, modal: null })
  })

  it('rejects out-of-range events and lists workspaces for switching', async () => {
    mount(<CommandPalette />)
    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: '#9999' } })
    expect(await screen.findByText(/Out of range: last event is #486/)).toBeTruthy()
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.click(screen.getByText('Switch workspace…'))
    expect(await screen.findByText('Agent behaviour study')).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' })
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
    expect(useUI.getState().workspaceId).toBe('w2')
  })
})
