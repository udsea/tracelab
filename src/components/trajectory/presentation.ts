import { eventLabel } from '@/lib/utils'
import type {
  EventPresentationClass,
  ReasoningVisibility,
} from '@/types/domain'
export function presentationLabel(
  type: string,
  visibility?: ReasoningVisibility | null,
) {
  if (type === 'reasoning' && visibility && visibility !== 'plaintext')
    return `${visibility[0].toUpperCase()}${visibility.slice(1)} reasoning`
  return eventLabel(type)
}
export function opaqueDescription(presentation?: EventPresentationClass) {
  return presentation === 'opaque'
    ? 'Provider reasoning state is preserved but not readable.'
    : null
}
export const eventModes = [
  ['all', 'All events'],
  ['tools', 'Tools'],
  ['reasoning', 'Reasoning'],
  ['errors', 'Errors'],
  ['runtime', 'Runtime'],
] as const
