import { useEffect, useMemo, useState, type ComponentType } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Command,
  Crosshair,
  Flag,
  FlaskConical,
  FolderOpen,
  GitBranch,
  Layers3,
  ListFilter,
  Play,
  Search,
  Settings2,
  SplitSquareHorizontal,
  Sun,
} from 'lucide-react'
import {
  useClassifiers,
  useTrajectories,
  useTrajectory,
  useWorkspaces,
} from '@/hooks/queries'
import { rpc } from '@/lib/api'
import { notify, useUI } from '@/stores/ui'
import type { DetectorDefinition } from '@/types/analysis'
import type { Metadata } from '@/types/domain'

type Mode = 'root' | 'trajectory' | 'detector' | 'workspace'
interface Item {
  id: string
  label: string
  hint?: string
  key?: string
  icon: ComponentType<{ size?: number }>
  disabled?: string
  keep?: boolean
  run: () => void | Promise<void>
}

/** "#214", "214", "go 214" or "event 214" address a canonical event index. */
export function parseEventQuery(query: string): number | null {
  const match = query.trim().match(/^(?:go(?: to)?|event)?\s*#?\s*(\d+)$/i)
  return match ? Number(match[1]) : null
}

const placeholders: Record<Mode, string> = {
  root: 'Type a command, or #214 to go to an event',
  trajectory: 'Open trajectory… filter by sample, condition or task',
  detector: 'Run detector… filter by name',
  workspace: 'Switch workspace… filter by name',
}

export function CommandPalette() {
  const ui = useUI()
  const [mode, setMode] = useState<Mode>('root')
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const client = useQueryClient()
  const trajectory = useTrajectory(ui.trajectoryId)
  const trajectories = useTrajectories(mode === 'trajectory' ? ui.workspaceId : null)
  const workspaces = useWorkspaces()
  const classifiers = useClassifiers()
  const detectors = useQuery({
    queryKey: ['detectors'],
    queryFn: () =>
      rpc<{ definitions: DetectorDefinition[]; templates: Record<string, Metadata> }>(
        'analysis.definitions',
      ),
    enabled: mode === 'detector',
  })
  const eventCount = trajectory.data?.trajectory.eventCount ?? 0
  const close = () => ui.set({ modal: null })
  const enter = (next: Mode) => {
    setMode(next)
    setQuery('')
    setActive(0)
  }
  async function runDetector(definition: {
    id?: string
    name: string
    detectorType: 'rule' | 'statistical'
    parameters: Metadata
  }) {
    if (!ui.trajectoryId) return
    const saved = definition.id
      ? definition
      : await rpc<DetectorDefinition>('analysis.save', definition)
    await rpc('analysis.run', {
      definitionId: saved.id,
      trajectoryIds: [ui.trajectoryId],
    })
    await client.invalidateQueries({ queryKey: ['jobs'] })
    notify(`${definition.name} started on this trajectory (local, no model calls)`)
  }
  const items: Item[] = useMemo(() => {
    const noTrajectory = ui.trajectoryId ? undefined : 'Open a trajectory first'
    if (mode === 'trajectory')
      return (trajectories.data?.items ?? []).map((t) => ({
        id: t.id,
        label: `sample_${t.sampleId}`,
        hint: [
          t.condition,
          t.parentTrajectoryId ? 'fork branch' : t.status,
          `${t.eventCount} recorded events`,
        ]
          .filter(Boolean)
          .join(' · '),
        icon: t.parentTrajectoryId ? GitBranch : Layers3,
        run: () => {
          ui.selectTrajectory(t.id)
          close()
        },
      }))
    if (mode === 'workspace')
      return (workspaces.data ?? []).map((w) => ({
        id: w.id,
        label: w.name,
        hint: w.isDemo ? 'Synthetic sample' : undefined,
        icon: FolderOpen,
        disabled: w.id === ui.workspaceId ? 'Current workspace' : undefined,
        run: () => {
          ui.setWorkspace(w.id)
          close()
        },
      }))
    if (mode === 'detector') {
      const saved = (detectors.data?.definitions ?? []).filter(
        (d) => d.detectorType === 'rule' || d.detectorType === 'statistical',
      )
      const savedNames = new Set(saved.map((d) => d.name))
      const templates = Object.entries(detectors.data?.templates ?? {})
        .filter(([, p]) => !savedNames.has(String(p.name)))
        .map(([key, p]) => ({
          id: `template:${key}`,
          label: String(p.name),
          hint: 'Rule template · local',
          icon: Play,
          disabled: noTrajectory,
          run: () =>
            runDetector({
              name: String(p.name),
              detectorType: 'rule',
              parameters: p,
            }).then(close),
        }))
      return [
        ...saved.map((d) => ({
          id: d.id,
          label: d.name,
          hint: `${d.detectorType === 'rule' ? 'Rule' : 'Statistical'} v${d.version} · local`,
          icon: Play,
          disabled: noTrajectory,
          run: () =>
            runDetector({
              id: d.id,
              name: d.name,
              detectorType: d.detectorType as 'rule' | 'statistical',
              parameters: d.parameters,
            }).then(close),
        })),
        ...templates,
        ...(classifiers.data ?? []).map((c) => ({
          id: `llm:${c.id}`,
          label: c.name,
          hint: 'Semantic / LLM · configure model before running',
          icon: FlaskConical,
          run: () => ui.openAnalysis('signals/semantic'),
        })),
      ]
    }
    const target = parseEventQuery(query)
    const goTo: Item[] =
      target === null
        ? []
        : [
            {
              id: 'go-to-event',
              label: `Go to event #${target}`,
              hint: `Canonical index · ${eventCount} recorded events (#0–${Math.max(0, eventCount - 1)})`,
              icon: Crosshair,
              keep: true,
              disabled: noTrajectory
                ? noTrajectory
                : !trajectory.data
                  ? 'Loading trajectory…'
                  : target >= eventCount
                  ? `Out of range: last event is #${eventCount - 1}`
                  : undefined,
              run: () => {
                ui.jump(target)
                close()
              },
            },
          ]
    return [
      ...goTo,
      {
        id: 'go-to',
        label: 'Go to event #…',
        hint: 'Type an index, for example #214',
        icon: Crosshair,
        disabled: noTrajectory,
        run: () => setQuery('#'),
      },
      {
        id: 'open-trajectory',
        label: 'Open trajectory…',
        icon: Layers3,
        run: () => enter('trajectory'),
      },
      {
        id: 'run-detector',
        label: 'Run detector…',
        hint: 'Rules and statistics run locally on this trajectory',
        icon: Play,
        run: () => enter('detector'),
      },
      {
        id: 'switch-workspace',
        label: 'Switch workspace…',
        icon: FolderOpen,
        run: () => enter('workspace'),
      },
      {
        id: 'search',
        label: 'Search workspace',
        key: '/',
        icon: Search,
        run: () => ui.set({ modal: 'search' }),
      },
      {
        id: 'import',
        label: 'Add trajectory source',
        key: '⌘O',
        icon: FolderOpen,
        run: () => ui.set({ modal: 'import' }),
      },
      {
        id: 'explorer',
        label: 'Open Explorer',
        icon: Layers3,
        run: () => ui.set({ section: 'trajectory', modal: null }),
      },
      {
        id: 'analysis',
        label: 'Open Analysis',
        icon: FlaskConical,
        run: () => ui.openAnalysis('overview'),
      },
      {
        id: 'forks',
        label: 'Open Fork Lab',
        icon: GitBranch,
        run: () => ui.set({ section: 'forks', modal: null }),
      },
      {
        id: 'compare',
        label: 'Open Comparisons',
        icon: SplitSquareHorizontal,
        run: () => ui.set({ section: 'compare', modal: null }),
      },
      {
        id: 'browse',
        label: 'Browse & filter trajectories',
        icon: ListFilter,
        run: () => ui.set({ section: 'browser', modal: null }),
      },
      {
        id: 'fork',
        label: `Fork from event #${ui.selectedIndex}`,
        key: 'F',
        icon: GitBranch,
        disabled:
          noTrajectory ??
          (trajectory.data?.capabilities.contextOnly
            ? undefined
            : trajectory.data?.capabilities.reason || 'Fork unavailable'),
        run: () => ui.set({ modal: 'fork' }),
      },
      {
        id: 'annotate',
        label: `Annotate event #${ui.selectedIndex}`,
        key: 'A',
        icon: Flag,
        disabled: noTrajectory,
        run: () => ui.set({ modal: 'annotate' }),
      },
      {
        id: 'jobs',
        label: 'Execution activity',
        icon: Activity,
        run: () => ui.set({ modal: 'jobs' }),
      },
      {
        id: 'settings',
        label: 'Provider settings',
        icon: Settings2,
        run: () => ui.set({ modal: 'settings' }),
      },
      {
        id: 'theme',
        label: 'Toggle light / dark theme',
        icon: Sun,
        run: () =>
          ui.set({ theme: ui.theme === 'dark' ? 'light' : 'dark', modal: null }),
      },
    ]
  }, [
    mode,
    query,
    ui,
    trajectory.data,
    trajectories.data,
    workspaces.data,
    detectors.data,
    classifiers.data,
    eventCount,
  ])
  const q = query.trim().toLowerCase()
  const visible = items.filter(
    (i) =>
      i.keep ||
      !q ||
      q === '#' ||
      `${i.label} ${i.hint ?? ''}`.toLowerCase().includes(q),
  )
  useEffect(() => setActive(0), [query, mode])
  const current = visible[Math.min(active, visible.length - 1)]
  const execute = (item?: Item) => {
    if (!item || item.disabled) return
    void Promise.resolve(item.run()).catch((e: Error) => notify(e.message))
  }
  const loading =
    (mode === 'trajectory' && trajectories.isLoading) ||
    (mode === 'detector' && detectors.isLoading)
  return (
    <div className="dialog-body command-dialog">
      <div className="search-input">
        {mode === 'root' ? (
          <Command size={16} />
        ) : (
          <button
            className="icon-button"
            aria-label="Back to all commands"
            onClick={() => enter('root')}
          >
            <ArrowLeft size={15} />
          </button>
        )}
        <input
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls="command-options"
          aria-activedescendant={current ? `command-${current.id}` : undefined}
          aria-label="Command"
          placeholder={placeholders[mode]}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => Math.min(visible.length - 1, a + 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => Math.max(0, a - 1))
            } else if (e.key === 'Enter') {
              e.preventDefault()
              execute(current)
            } else if (e.key === 'Backspace' && !query && mode !== 'root') {
              enter('root')
            }
          }}
        />
      </div>
      <div id="command-options" role="listbox" aria-label="Commands">
        {loading && <p className="muted small command-empty">Loading…</p>}
        {!loading && !visible.length && (
          <p className="muted small command-empty">No matching commands.</p>
        )}
        {visible.map((item) => (
          <button
            id={`command-${item.id}`}
            role="option"
            aria-selected={item === current}
            aria-disabled={!!item.disabled}
            className={`command-row ${item === current ? 'active' : ''}`}
            key={item.id}
            title={item.disabled}
            onMouseEnter={() => setActive(visible.indexOf(item))}
            onClick={() => execute(item)}
          >
            <item.icon size={16} />
            <span className="command-label">
              {item.label}
              {(item.disabled || item.hint) && (
                <small>{item.disabled ?? item.hint}</small>
              )}
            </span>
            {item.key && <kbd>{item.key}</kbd>}
            <ArrowRight size={13} />
          </button>
        ))}
      </div>
      <p className="command-footer muted small">
        ↑↓ to move · Enter to run · Backspace to go back · Esc to close
      </p>
    </div>
  )
}
