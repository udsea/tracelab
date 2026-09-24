import { ChevronRight, Command, Moon, Orbit, Search, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useWorkspaces } from '@/hooks/queries'
import { useUI } from '@/stores/ui'

const sectionNames = {
  trajectory: 'Explorer',
  classifiers: 'Analysis',
  forks: 'Fork lab',
  compare: 'Comparisons',
  browser: 'Browse',
} as const

/** App chrome holds navigation and global tools; contextual actions live with their content. */
export function TopBar() {
  const ui = useUI()
  const workspaces = useWorkspaces()
  const workspace = workspaces.data?.find((w) => w.id === ui.workspaceId)
  return (
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
        <strong>{sectionNames[ui.section]}</strong>
      </span>
      <div className="topbar-spacer" />
      <button
        className="global-search"
        aria-keyshortcuts="/"
        onClick={() => ui.set({ modal: 'search' })}
      >
        <Search size={13} />
        <span>Search…</span>
        <kbd>/</kbd>
      </button>
      <button
        className="global-search global-commands"
        aria-keyshortcuts="Meta+K Control+K"
        onClick={() => ui.set({ modal: 'commands' })}
      >
        <Command size={13} />
        <span>Commands</span>
        <kbd>⌘K</kbd>
      </button>
      <Button
        variant="ghost"
        size="icon"
        title="Toggle theme"
        aria-label="Toggle light / dark theme"
        onClick={() => ui.set({ theme: ui.theme === 'dark' ? 'light' : 'dark' })}
      >
        {ui.theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
      </Button>
    </header>
  )
}
