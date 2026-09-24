import { RunOutline } from '@/features/analysis/RunOutline'
import {
  ChevronDown,
  ChevronsLeft,
  FlaskConical,
  FolderOpen,
  GitBranch,
  Layers3,
  ListFilter,
  Plus,
  Settings2,
  SplitSquareHorizontal,
} from 'lucide-react'
import { useExperiments, useTrajectories, useWorkspaces } from '@/hooks/queries'
import { useUI } from '@/stores/ui'
import { Status } from '@/components/common/Primitives'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
export function Sidebar() {
  const ui = useUI()
  const workspaces = useWorkspaces()
  const experiments = useExperiments(ui.workspaceId)
  const trajectories = useTrajectories(ui.workspaceId)
  const workspace = workspaces.data?.find((w) => w.id === ui.workspaceId)
  return (
    <aside className="sidebar">
      <button
        className="workspace-switch"
        onClick={() => ui.setWorkspace(null)}
      >
        <div className="workspace-monogram">{workspace?.name[0] || 'W'}</div>
        <span>
          <strong>{workspace?.name || 'Workspace'}</strong>
          <small>Research workspace</small>
        </span>
        <ChevronsLeft size={14} />
      </button>
      <nav className="section-nav">
        {(
          [
            ['trajectory', Layers3, 'Trajectory explorer'],
            ['classifiers', FlaskConical, 'Analysis'],
            ['forks', GitBranch, 'Fork lab'],
            ['compare', SplitSquareHorizontal, 'Comparisons'],
          ] as const
        ).map(([key, Icon, label]) => (
          <button
            key={key}
            className={cn(ui.section === key && 'active')}
            onClick={() => ui.set({ section: key })}
          >
            <Icon size={15} />
            {label}
            {key === 'classifiers' && <span className="nav-dot" />}
          </button>
        ))}
      </nav>
      <div className="sidebar-heading">
        EXPERIMENTS
        <Button
          variant="ghost"
          size="icon"
          title="Add trajectory source"
          onClick={() => ui.set({ modal: 'import' })}
        >
          <Plus size={13} />
        </Button>
      </div>
      <div className="experiment-tree">
        {experiments.data?.map((experiment) => (
          <div key={experiment.id}>
            <div className="experiment-label" title={experiment.sourcePath}>
              <ChevronDown size={12} />
              <FolderOpen size={14} />
              <span>
                {experiment.name.replace('Session authentication · ', '')}
              </span>
              <span className="tree-count">
                {experiment.trajectoryCount ?? 0}
              </span>
            </div>
            {trajectories.data?.items
              .filter(
                (t) =>
                  t.experimentId === experiment.id && !t.parentTrajectoryId,
              )
              .map((t) => (
                <button
                  key={t.id}
                  onClick={() => ui.selectTrajectory(t.id)}
                  className={cn(
                    'trajectory-link',
                    ui.trajectoryId === t.id && 'selected',
                  )}
                >
                  <span className="tree-elbow" />
                  <Status status={t.status} small />
                  <span>sample_{t.sampleId}</span>
                  <span className="tree-count">
                    {t.loaded ? t.eventCount : '…'}
                  </span>
                </button>
              ))}
          </div>
        ))}
      </div>
      <button
        className="browse-all"
        onClick={() => ui.set({ section: 'browser' })}
      >
        <ListFilter size={13} />
        Browse & filter all trajectories
        <span>{trajectories.data?.total || 0}</span>
      </button>
      {ui.trajectoryId && <RunOutline />}
      <div className="sidebar-footer">
        <span className="local-indicator">
          <i />
          Local · DuckDB
        </span>
        <Button
          variant="ghost"
          size="icon"
          title="Provider settings"
          onClick={() => ui.set({ modal: 'settings' })}
        >
          <Settings2 size={15} />
        </Button>
      </div>
    </aside>
  )
}
