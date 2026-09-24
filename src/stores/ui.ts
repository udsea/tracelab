import { create } from 'zustand'
import { persist } from 'zustand/middleware'
export type Section =
  | 'trajectory'
  | 'classifiers'
  | 'forks'
  | 'compare'
  | 'browser'
export type AnalysisTab =
  | 'overview'
  | 'signals/semantic'
  | 'signals/rules'
  | 'signals/statistical'
  | 'signals/environment'
  | 'compare'
  | 'internals/graph'
  | 'internals/imported'
  | 'notes'
/** Sections whose content belongs to the selected trajectory and its run outline. */
export const outlineSections: Section[] = ['trajectory', 'classifiers']
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
  analysisTab: AnalysisTab
  modal: Modal
  mode: string
  expanded: boolean
  theme: 'dark' | 'light'
  range: { start: number; end: number; label: string } | null
  scale: 'events' | 'time' | 'calls'
  signalId: string | null
  rangeHistory: ({ start: number; end: number; label: string } | null)[]
  focus: (start: number, end: number, label: string) => void
  backRange: () => void
  hiddenLanes: string[]
  comparisonRight: string | null
  resultId: string | null
  toast: string | null
  setWorkspace: (id: string | null) => void
  selectTrajectory: (id: string) => void
  jump: (index: number) => void
  select: (index: number) => void
  openAnalysis: (tab: AnalysisTab) => void
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
      analysisTab: 'overview',
      modal: null,
      mode: 'all',
      expanded: false,
      theme: 'dark',
      range: null,
      scale: 'events',
      signalId: null,
      rangeHistory: [],
      focus: (start, end, label) =>
        set((state) => ({
          rangeHistory: [...state.rangeHistory, state.range].slice(-30),
          range: { start, end, label },
          selectedIndex: start,
          jumpVersion: state.jumpVersion + 1,
          section: 'trajectory',
          mode: 'all',
        })),
      backRange: () =>
        set((state) => ({
          range: state.rangeHistory.at(-1) ?? null,
          rangeHistory: state.rangeHistory.slice(0, -1),
        })),
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
          rangeHistory: [],
          signalId: null,
        }),
      selectTrajectory: (id) =>
        set({
          trajectoryId: id,
          selectedIndex: 0,
          section: 'trajectory',
          range: null,
          rangeHistory: [],
          signalId: null,
          mode: 'all',
        }),
      jump: (index) =>
        set((state) => ({
          selectedIndex: index,
          jumpVersion: state.jumpVersion + 1,
          mode: 'all',
          rangeHistory: state.range
            ? [...state.rangeHistory, state.range].slice(-30)
            : state.rangeHistory,
          range: null,
          section: 'trajectory',
        })),
      select: (index) => set({ selectedIndex: index }),
      openAnalysis: (tab) =>
        set({ section: 'classifiers', analysisTab: tab, modal: null }),
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
