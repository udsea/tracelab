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
import { outlineSections, useUI } from '@/stores/ui'
import { Status } from '@/components/common/Primitives'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Trajectory } from '@/types/domain'
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
        {experiments.data?.map((experiment) => {
          const items =
            trajectories.data?.items.filter(
              (t) => t.experimentId === experiment.id,
            ) ?? []
          const branches = items.filter((t) => t.parentTrajectoryId).length
          const runs = (experiment.trajectoryCount ?? 0) - branches
          return (
            <div key={experiment.id}>
              <div className="experiment-label" title={experiment.sourcePath}>
                <ChevronDown size={12} />
                <FolderOpen size={14} />
                <span>
                  {experiment.name.replace('Session authentication · ', '')}
                </span>
                <span
                  className="tree-count"
                  title={`${runs} runs${branches ? ` · ${branches} fork branches` : ''}`}
                >
                  {runs}
                </span>
              </div>
              {items
                .filter((t) => !t.parentTrajectoryId)
                .map((t) => (
                  <div key={t.id}>
                    <TrajectoryLink trajectory={t} />
                    {items
                      .filter((c) => c.parentTrajectoryId === t.id)
                      .map((c) => (
                        <TrajectoryLink key={c.id} trajectory={c} branch />
                      ))}
                  </div>
                ))}
            </div>
          )
        })}
      </div>
      <button
        className="browse-all"
        onClick={() => ui.set({ section: 'browser' })}
      >
        <ListFilter size={13} />
        Browse & filter all trajectories
        <span>{trajectories.data?.total || 0}</span>
      </button>
      {ui.trajectoryId && (
        // Hidden rather than unmounted so its local state survives a visit elsewhere.
        <div
          className="run-outline-slot"
          hidden={!outlineSections.includes(ui.section)}
          data-testid="run-outline-slot"
        >
          <RunOutline />
        </div>
      )}
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
function TrajectoryLink({
  trajectory: t,
  branch = false,
}: {
  trajectory: Trajectory
  branch?: boolean
}) {
  const ui = useUI()
  return (
    <button
      onClick={() => ui.selectTrajectory(t.id)}
      className={cn(
        'trajectory-link',
        branch && 'trajectory-branch',
        ui.trajectoryId === t.id && 'selected',
      )}
      aria-current={ui.trajectoryId === t.id ? 'true' : undefined}
    >
      <span className="tree-elbow" />
      {branch ? (
        <GitBranch size={11} aria-label="Fork branch" />
      ) : (
        <Status status={t.status} small />
      )}
      <span>
        {branch
          ? t.sampleId.replace(/^.* \/ /, '')
          : `sample_${t.sampleId}`}
      </span>
      <span
        className="tree-count"
        title={t.loaded ? `${t.eventCount} recorded events` : 'Not indexed yet'}
      >
        {t.loaded ? t.eventCount : '…'}
      </span>
    </button>
  )
}
