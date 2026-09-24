import { Component, useEffect, useRef, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  ChevronRight,
  Command,
  FlaskConical,
  GitBranch,
  HelpCircle,
  LoaderCircle,
  Moon,
  Orbit,
  Search,
  Sun,
  X,
} from 'lucide-react'
import { Welcome } from '@/features/workspace/Welcome'
import { Sidebar } from '@/features/workspace/Sidebar'
import { WorkspaceDialogs } from '@/features/workspace/Dialogs'
import { TrajectoryView } from '@/components/trajectory/TrajectoryView'
import { EventInspector } from '@/components/trajectory/EventInspector'
import { Timeline } from '@/components/timeline/Timeline'
import { AnalysisWorkspace } from '@/features/analysis/AnalysisWorkspace'
import { SignalInspector } from '@/features/analysis/SignalInspector'
import { ForkDialog, ForkWorkspace } from '@/features/forks/ForkLab'
import { ComparisonWorkspace } from '@/features/comparisons/ComparisonWorkspace'
import { TrajectoryBrowser } from '@/features/trajectories/TrajectoryBrowser'
import { EvidenceDialog } from '@/components/classifier/EvidenceDialog'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/common/Primitives'
import {
  useJobs,
  useTrajectories,
  useTrajectory,
  useWorkspaces,
} from '@/hooks/queries'
import { rpc } from '@/lib/api'
import { notify, useUI } from '@/stores/ui'
export function App() {
  const ui = useUI()
  const jobs = useJobs()
  const workspaces = useWorkspaces()
  const trajectories = useTrajectories(ui.workspaceId)
  const selectedTrajectory = useTrajectory(ui.trajectoryId)
  const client = useQueryClient()
  const previousJobs = useRef('')
  const workspace = workspaces.data?.find((w) => w.id === ui.workspaceId)
  const active =
    jobs.data?.filter((j) => j.status === 'running' || j.status === 'queued') ||
    []
  useEffect(() => {
    document.documentElement.dataset.theme = ui.theme
  }, [ui.theme])
  useEffect(() => {
    if (ui.workspaceId)
      void rpc('workspaces.open', { id: ui.workspaceId })
        .then(() => client.invalidateQueries({ queryKey: ['workspaces'] }))
        .catch((error: Error) => notify(error.message))
  }, [ui.workspaceId, client])
  useEffect(() => {
    if (!ui.trajectoryId && trajectories.data?.items[0])
      ui.selectTrajectory(trajectories.data.items[0].id)
  }, [ui.trajectoryId, trajectories.data])
  useEffect(() => {
    const signature =
      jobs.data?.map((j) => `${j.id}:${j.status}:${j.completed}`).join('|') ||
      ''
    if (previousJobs.current && previousJobs.current !== signature) {
      for (const key of [
        'workspaces',
        'experiments',
        'trajectories',
        'trajectory',
        'events',
        'event',
        'timeline',
        'overview',
        'signals',
        'signal',
        'forks',
        'browse',
        'comparison',
        'analysis-comparison',
        'search',
        'trajectory-picker',
        'trajectory-summary',
      ])
        void client.invalidateQueries({ queryKey: [key] })
    }
    previousJobs.current = signature
  }, [jobs.data, client])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const cmd = event.metaKey || event.ctrlKey
      const input = (event.target as HTMLElement)?.closest(
        'input,textarea,select,[contenteditable]',
      )
      if (cmd && event.key.toLowerCase() === 'o') {
        event.preventDefault()
        ui.set({ modal: 'import' })
        return
      }
      if (cmd && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        ui.set({ modal: 'commands' })
        return
      }
      if (input || ui.modal || ui.resultId) return
      if (event.key === '/') {
        event.preventDefault()
        ui.set({ modal: 'search' })
      }
      if (
        ui.trajectoryId &&
        selectedTrajectory.data?.capabilities.contextOnly &&
        event.key.toLowerCase() === 'f'
      )
        ui.set({ modal: 'fork' })
      if (ui.trajectoryId && event.key.toLowerCase() === 'a')
        ui.set({ modal: 'annotate' })
      if (ui.trajectoryId && ['j', 'k'].includes(event.key)) {
        const t = selectedTrajectory.data?.trajectory
        ui.jump(
          Math.max(
            0,
            Math.min(
              (t?.eventCount || 1) - 1,
              ui.selectedIndex + (event.key === 'j' ? 1 : -1),
            ),
          ),
        )
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [ui, selectedTrajectory.data])
  useEffect(() => {
    if (ui.toast) {
      const id = setTimeout(() => ui.set({ toast: null }), 6500)
      return () => clearTimeout(id)
    }
  }, [ui.toast])
  return (
    <Boundary>
      <div className="app-shell">
        {!ui.workspaceId ? (
          <Welcome />
        ) : (
          <>
            <header className="topbar">
              <button className="brand" onClick={() => ui.setWorkspace(null)}>
                <span className="brand-icon">
                  <Orbit size={21} />
                </span>
                TraceLab
              </button>
              <span className="topbar-divider" />
              <span className="topbar-context">
                {workspace?.name || 'Workspace'}
                <ChevronRight size={12} />
                <strong>
                  {ui.section === 'trajectory'
                    ? 'Explorer'
                    : ui.section === 'classifiers'
                      ? 'Analysis'
                      : ui.section[0].toUpperCase() + ui.section.slice(1)}
                </strong>
              </span>
              <div className="topbar-spacer" />
              <button
                className="global-search"
                onClick={() => ui.set({ modal: 'search' })}
              >
                <Search size={13} />
                <span>Search trajectories…</span>
                <kbd>⌘ K</kbd>
              </button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => ui.set({ section: 'classifiers' })}
              >
                <FlaskConical size={14} />
                Analyse
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={!selectedTrajectory.data?.capabilities.contextOnly}
                title={selectedTrajectory.data?.capabilities.reason}
                onClick={() => ui.set({ modal: 'fork' })}
              >
                <GitBranch size={14} />
                Fork
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title="Toggle theme"
                onClick={() =>
                  ui.set({ theme: ui.theme === 'dark' ? 'light' : 'dark' })
                }
              >
                {ui.theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
              </Button>
            </header>
            <div className="workspace-shell">
              <Sidebar />
              <main className="main-shell">
                {workspace?.isDemo && (
                  <div className="demo-banner">
                    <span className="demo-label">SAMPLE WORKSPACE</span>
                    <span>
                      Trajectories, outcomes, and signal curves are synthetic
                      examples.
                    </span>
                    <button onClick={() => ui.set({ modal: 'import' })}>
                      Open your own logs
                      <ChevronRight size={11} />
                    </button>
                  </div>
                )}
                {ui.section === 'trajectory' ? (
                  <>
                    <div className="ide-panes">
                      <TrajectoryView />
                      <EventInspector />
                    </div>
                    <Timeline />
                  </>
                ) : ui.section === 'classifiers' ? (
                  <AnalysisWorkspace />
                ) : ui.section === 'forks' ? (
                  <ForkWorkspace />
                ) : ui.section === 'compare' ? (
                  <ComparisonWorkspace />
                ) : (
                  <TrajectoryBrowser />
                )}
              </main>
            </div>
            <footer className="statusbar">
              <span>
                <span className="green-dot" />
                All changes stored locally
              </span>
              <span className="statusbar-divider" />
              <button onClick={() => ui.set({ modal: 'jobs' })}>
                {active.length ? (
                  <LoaderCircle size={11} className="spin" />
                ) : (
                  <Activity size={11} />
                )}{' '}
                {active.length
                  ? `${active.length} active jobs · ${active[0].completed}/${active[0].total || '…'} ${active[0].name}`
                  : 'No running jobs'}
              </button>
              <div className="topbar-spacer" />
              <span>Inspect AI</span>
              <button onClick={() => ui.set({ modal: 'commands' })}>
                <Command size={10} /> K <span>Commands</span>
              </button>
              <button
                title="Keyboard shortcuts: Cmd/Ctrl+O open, Cmd/Ctrl+K commands, / search, J/K events, A annotate, F fork"
                onClick={() => ui.set({ modal: 'commands' })}
              >
                <HelpCircle size={12} />
              </button>
            </footer>
          </>
        )}
        <WorkspaceDialogs />
        <ForkDialog />
        <EvidenceDialog />
        <SignalInspector />
        {ui.toast && (
          <div className="toast" role="status">
            <span>{ui.toast}</span>
            <button
              className="icon-button"
              onClick={() => ui.set({ toast: null })}
              aria-label="Dismiss notification"
            >
              <X size={13} />
            </button>
          </div>
        )}
      </div>
    </Boundary>
  )
}
class Boundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    return this.state.error ? (
      <ErrorState
        error={this.state.error}
        retry={() => window.location.reload()}
      />
    ) : (
      this.props.children
    )
  }
}
