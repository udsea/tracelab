import { create } from 'zustand'
import { persist } from 'zustand/middleware'
type Section = 'trajectory' | 'classifiers' | 'forks' | 'compare' | 'browser'
type Modal =
  | 'import'
  | 'search'
  | 'commands'
  | 'settings'
  | 'fork'
  | 'annotate'
  | 'segment'
  | 'jobs'
  | null
interface UIState {
  workspaceId: string | null
  trajectoryId: string | null
  selectedIndex: number
  jumpVersion: number
  section: Section
  modal: Modal
  mode: string
  expanded: boolean
  theme: 'dark' | 'light'
  range: { start: number; end: number; label: string } | null
  hiddenLanes: string[]
  comparisonRight: string | null
  resultId: string | null
  toast: string | null
  setWorkspace: (id: string | null) => void
  selectTrajectory: (id: string) => void
  jump: (index: number) => void
  select: (index: number) => void
  set: (value: Partial<UIState>) => void
}
export const useUI = create<UIState>()(
  persist(
    (set) => ({
      workspaceId: null,
      trajectoryId: null,
      selectedIndex: 0,
      jumpVersion: 0,
      section: 'trajectory',
      modal: null,
      mode: 'all',
      expanded: false,
      theme: 'dark',
      range: null,
      hiddenLanes: [],
      comparisonRight: null,
      resultId: null,
      toast: null,
      setWorkspace: (id) =>
        set({
          workspaceId: id,
          trajectoryId: null,
          selectedIndex: 0,
          section: 'trajectory',
          range: null,
        }),
      selectTrajectory: (id) =>
        set({
          trajectoryId: id,
          selectedIndex: 0,
          section: 'trajectory',
          range: null,
          mode: 'all',
        }),
      jump: (index) =>
        set((state) => ({
          selectedIndex: index,
          jumpVersion: state.jumpVersion + 1,
          mode: 'all',
          range: null,
          section: 'trajectory',
        })),
      select: (index) => set({ selectedIndex: index }),
      set,
    }),
    {
      name: 'tracelab-ui',
      partialize: (state) => ({
        workspaceId: state.workspaceId,
        trajectoryId: state.trajectoryId,
        theme: state.theme,
        hiddenLanes: state.hiddenLanes,
      }),
    },
  ),
)
export function notify(message: string) {
  useUI.getState().set({ toast: message })
}
