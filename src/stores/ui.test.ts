import { describe, expect, it, vi } from 'vitest'
vi.hoisted(() => {
  Object.defineProperty(globalThis, 'window', {
    value: {
      localStorage: {
        getItem: () => null,
        setItem: () => {},
        removeItem: () => {},
      },
    },
    configurable: true,
  })
})
import { useUI } from './ui'
describe('trajectory navigation', () => {
  it('evidence jumps clear filters so the cited event is reachable', () => {
    useUI
      .getState()
      .set({
        range: { start: 20, end: 50, label: 'Phase' },
        mode: 'tools',
        section: 'classifiers',
      })
    useUI.getState().jump(184)
    expect(useUI.getState()).toMatchObject({
      range: null,
      mode: 'all',
      selectedIndex: 184,
      section: 'trajectory',
    })
  })
  it('switching workspaces clears trajectory selection and ranges', () => {
    useUI.getState().selectTrajectory('parent')
    useUI.getState().set({ range: { start: 2, end: 4, label: 'Old phase' } })
    useUI.getState().setWorkspace('new-workspace')
    expect(useUI.getState()).toMatchObject({
      trajectoryId: null,
      workspaceId: 'new-workspace',
      range: null,
    })
  })
})
