import { useState } from 'react'
import {
  ArrowRight,
  Clock3,
  Command,
  FlaskConical,
  FolderOpen,
  GitBranch,
  Layers3,
  Orbit,
  Plus,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAction, useWorkspaces } from '@/hooks/queries'
import { useUI } from '@/stores/ui'
import { ErrorState, Loading } from '@/components/common/Primitives'
import type { Workspace } from '@/types/domain'
export function Welcome() {
  const workspaces = useWorkspaces()
  const setWorkspace = useUI((s) => s.setWorkspace)
  const set = useUI((s) => s.set)
  const demo = useAction<Workspace>('workspaces.demo', [
    'workspaces',
    'experiments',
    'trajectories',
  ])
  const create = useAction<Workspace>('workspaces.create', ['workspaces'])
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  async function open(id: string) {
    setWorkspace(id)
  }
  return (
    <div className="welcome">
      <header className="welcome-header">
        <div className="brand">
          <span className="brand-icon">
            <Orbit size={22} />
          </span>
          TraceLab <span className="version">v0.1</span>
        </div>
        <span className="local-indicator">
          <i /> Local workspace
        </span>
      </header>
      <div className="welcome-body">
        <div className="welcome-kicker">
          <span /> THE TRAJECTORY WORKBENCH
        </div>
        <h1>
          Follow the agent.
          <br />
          <span>Understand the trajectory.</span>
        </h1>
        <p className="welcome-lead">
          A research IDE for the moments between a task and its outcome.
          <br />
          Explore behaviour, trace evidence, and test interventions.
        </p>
        <div className="welcome-actions">
          <Button
            onClick={() => {
              setWorkspace(null)
              set({ modal: 'import' })
            }}
          >
            <FolderOpen size={16} />
            Add trajectory source<kbd>⌘ O</kbd>
          </Button>
          <Button
            variant="ghost"
            disabled={demo.isPending}
            onClick={() =>
              demo.mutate(
                {},
                {
                  onSuccess: (w) => {
                    void open(w.id)
                  },
                },
              )
            }
          >
            {demo.isPending
              ? 'Preparing sample…'
              : 'Explore a sample workspace'}
            <ArrowRight size={15} />
          </Button>
        </div>
        <div className="welcome-columns">
          <section className="recent">
            <div className="section-label">
              RECENT WORKSPACES
              <Button
                size="icon"
                variant="ghost"
                title="Create workspace"
                onClick={() => setCreating(!creating)}
              >
                <Plus size={14} />
              </Button>
            </div>
            {creating && (
              <form
                className="new-workspace"
                onSubmit={(e) => {
                  e.preventDefault()
                  create.mutate(
                    { name: name || 'Untitled workspace' },
                    {
                      onSuccess: (w) => {
                        void open(w.id)
                      },
                    },
                  )
                }}
              >
                <input
                  autoFocus
                  placeholder="Workspace name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <Button size="sm" type="submit">
                  Create
                </Button>
              </form>
            )}
            {workspaces.isLoading && <Loading text="Opening local storage…" />}
            {workspaces.error && (
              <ErrorState
                error={workspaces.error}
                retry={() => {
                  void workspaces.refetch()
                }}
              />
            )}
            {workspaces.data?.map((w) => (
              <button
                className="workspace-row"
                key={w.id}
                onClick={() => {
                  void open(w.id)
                }}
              >
                <div className="workspace-symbol">
                  <Layers3 size={19} />
                </div>
                <div>
                  <strong>{w.name}</strong>
                  <span>
                    {w.isDemo
                      ? 'Synthetic examples'
                      : `${w.sources.length} Inspect log locations`}
                  </span>
                </div>
                <ArrowRight size={16} />
              </button>
            ))}
            {workspaces.data?.length === 0 && (
              <div className="recent-empty">
                <Clock3 size={17} />
                <p>
                  Your research starts here.
                  <br />
                  <span>Open a log or explore the sample workspace.</span>
                </p>
              </div>
            )}
          </section>
          <section className="welcome-note">
            <div className="mini-trace">
              <i />
              <i />
              <i />
              <i />
              <span />
              <i />
              <i />
            </div>
            <h3>More than a transcript.</h3>
            <p>
              See long trajectories as phases, signals, and decisions. Keep
              every analysis linked to the events that support it.
            </p>
            <div className="feature-tags">
              <span>
                <Layers3 size={13} />
                Explore
              </span>
              <span>
                <FlaskConical size={13} />
                Classify
              </span>
              <span>
                <GitBranch size={13} />
                Intervene
              </span>
            </div>
          </section>
        </div>
      </div>
      <footer className="welcome-footer">
        <span>Built around Inspect AI. Your logs stay yours.</span>
        <span>
          <Command size={12} /> K <span className="muted">Command palette</span>
        </span>
      </footer>
    </div>
  )
}
