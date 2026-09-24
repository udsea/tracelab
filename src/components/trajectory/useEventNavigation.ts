import { useEffect, useRef, useState } from 'react'
import { rpc } from '@/lib/api'
import type { EventLocation } from '@/types/domain'

export interface EventView {
  trajectoryId: string | null
  mode: string
  start?: number
  end?: number
  query?: string
}

/** Navigation requests have their own identity; a normal row selection is not one. */
export function useEventNavigation(
  view: EventView,
  selectedIndex: number,
  jumpVersion: number,
  total: number | undefined,
  scroll: (offset: number) => void,
  selectInitial?: (eventIndex: number) => void,
) {
  const initial = useRef({
    trajectoryId: view.trajectoryId,
    jumpVersion,
    pending: true,
  })
  if (initial.current.trajectoryId !== view.trajectoryId)
    initial.current = {
      trajectoryId: view.trajectoryId,
      jumpVersion,
      pending: true,
    }
  const selectInitialRef = useRef(selectInitial)
  selectInitialRef.current = selectInitial
  const selected = useRef(selectedIndex)
  selected.current = selectedIndex
  const scrollRef = useRef(scroll)
  scrollRef.current = scroll
  const key = JSON.stringify([
    view.trajectoryId,
    view.mode,
    view.start,
    view.end,
    view.query,
    jumpVersion,
  ])
  const [result, setResult] = useState<{
    key: string
    location?: EventLocation
    error?: string
  }>()
  const completed = useRef<string | null>(null)
  const previousKey = useRef(key)
  if (previousKey.current !== key) {
    previousKey.current = key
    completed.current = null
  }
  useEffect(() => {
    if (!view.trajectoryId || total === undefined || completed.current === key)
      return
    let cancelled = false
    const eventIndex = selected.current
    void rpc<EventLocation>('events.locate', { ...view, eventIndex })
      .then((location) => {
        if (cancelled) return
        completed.current = key
        if (selected.current !== eventIndex) {
          initial.current.pending = false
          return
        }
        // The default selection on opening a trajectory is canonical zero, which
        // may be bookkeeping. Explicit jumps and later filters retain selection.
        if (
          initial.current.pending &&
          initial.current.jumpVersion === jumpVersion &&
          view.mode === 'all' &&
          view.start === undefined &&
          eventIndex === 0 &&
          !location.exact &&
          location.nearestEventIndex != null
        )
          selectInitialRef.current?.(location.nearestEventIndex)
        initial.current.pending = false
        setResult({ key, location })
        if (location.offset !== null) scrollRef.current(location.offset)
      })
      .catch((error) => {
        if (!cancelled) setResult({ key, error: String(error) })
      })
    return () => {
      cancelled = true
    }
    // Selection and virtualizer identity deliberately do not trigger navigation.
  }, [key, total])
  return result?.key === key ? result : undefined
}
