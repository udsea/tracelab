import type { Intervention, TrajectoryEvent } from '@/types/domain'

/** Mirrors backend `GENERATION_PARAMETERS`; the backend remains the authority. */
export const GENERATION_PARAMETERS = [
  'temperature',
  'max_tokens',
  'top_p',
  'top_k',
  'seed',
  'reasoning_effort',
  'reasoning_tokens',
  'stop_seqs',
] as const
const COMMON = new Set(['temperature', 'max_tokens', 'seed'])

export interface GenerationForm {
  temperature: string
  maxTokens: string
  seed: string
  advanced: string
}
export const defaultGeneration: GenerationForm = {
  temperature: '',
  maxTokens: '2048',
  seed: '',
  advanced: '',
}

/** Empty common fields are omitted so the provider default applies. */
export function buildGenerationParameters(form: GenerationForm): {
  parameters: Record<string, unknown>
  error: string | null
} {
  const parameters: Record<string, unknown> = {}
  if (form.temperature.trim()) {
    const value = Number(form.temperature)
    if (!Number.isFinite(value) || value < 0 || value > 2)
      return { parameters, error: 'Temperature must be a number from 0 to 2.' }
    parameters.temperature = value
  }
  if (form.maxTokens.trim()) {
    const value = Number(form.maxTokens)
    if (!Number.isInteger(value) || value < 1)
      return { parameters, error: 'Max tokens must be a positive whole number.' }
    parameters.max_tokens = value
  }
  if (form.seed.trim()) {
    const value = Number(form.seed)
    if (!Number.isInteger(value))
      return { parameters, error: 'Seed must be a whole number.' }
    parameters.seed = value
  }
  if (form.advanced.trim()) {
    let extra: unknown
    try {
      extra = JSON.parse(form.advanced)
    } catch {
      return { parameters, error: 'Advanced parameters must be valid JSON.' }
    }
    if (!extra || typeof extra !== 'object' || Array.isArray(extra))
      return { parameters, error: 'Advanced parameters must be a JSON object.' }
    for (const [key, value] of Object.entries(extra)) {
      if (COMMON.has(key))
        return {
          parameters,
          error: `Set ${key} with its field above, not in advanced JSON.`,
        }
      if (!(GENERATION_PARAMETERS as readonly string[]).includes(key))
        return {
          parameters,
          error: `Unsupported parameter "${key}". Supported: ${GENERATION_PARAMETERS.filter((k) => !COMMON.has(k)).join(', ')}.`,
        }
      parameters[key] = value
    }
  }
  return { parameters, error: null }
}

export type EditorIntervention = {
  key: number
  type: Intervention['type']
  targetIndex: number
  text: string
  /** Original event content for replacements, once loaded. */
  original: string | null
  role: string
}

const editableText = new Set(['system', 'user', 'assistant', 'reasoning'])

export function originalFor(
  type: Intervention['type'],
  event: TrajectoryEvent | undefined,
): string | null {
  if (!event) return null
  if (type === 'replace_tool_result') {
    const result = event.tool?.result
    return result == null
      ? ''
      : typeof result === 'string'
        ? JSON.stringify(result)
        : JSON.stringify(result, null, 2)
  }
  if (type === 'replace_content') return event.content ?? ''
  return null
}

/** Why a context-only replacement cannot target this event, if it cannot. */
export function replacementBlocked(event: TrajectoryEvent | undefined) {
  if (!event) return null
  if (event.metadata.presentationClass === 'opaque')
    return 'Opaque reasoning cannot be edited as text.'
  const block = event.metadata.contentBlock as { signature?: unknown } | undefined
  if (block?.signature) return 'Signed reasoning cannot be edited; remove it instead.'
  if (event.type === 'tool_call')
    return 'A tool call is not editable model text; replace its result instead.'
  if (!editableText.has(event.type) && event.type !== 'tool_result')
    return 'This event is not model context.'
  return null
}

/** The first intervention starts from the selected event and its original content. */
export function defaultIntervention(
  event: TrajectoryEvent | undefined,
  index: number,
): EditorIntervention {
  const base = { key: 0, targetIndex: index, role: 'user' }
  if (!event || replacementBlocked(event))
    return { ...base, type: 'append_message', text: '', original: null }
  const structured =
    event.type === 'tool_result' &&
    event.tool?.result != null &&
    typeof event.tool.result !== 'string'
  const type = structured ? 'replace_tool_result' : 'replace_content'
  const original = originalFor(type, event)
  return { ...base, type, text: original ?? '', original }
}

export const targets = (type: Intervention['type']) =>
  type === 'remove_event' ||
  type === 'replace_content' ||
  type === 'replace_tool_result'

export function toInterventions(
  trajectoryId: string,
  items: EditorIntervention[],
): { interventions: Intervention[]; error: string | null } {
  const interventions: Intervention[] = []
  for (const item of items) {
    const eventId = `${trajectoryId}:e${item.targetIndex}`
    if (item.type === 'remove_event') interventions.push({ type: item.type, eventId })
    else if (item.type === 'replace_content')
      interventions.push({ type: item.type, eventId, content: item.text })
    else if (item.type === 'replace_tool_result') {
      try {
        interventions.push({ type: item.type, eventId, value: JSON.parse(item.text) })
      } catch {
        return {
          interventions,
          error: `Replacement tool result for #${item.targetIndex} must be valid JSON (wrap text in quotes).`,
        }
      }
    } else if (item.type === 'append_message')
      interventions.push({ type: item.type, role: item.role, content: item.text })
    else if (item.type === 'system_prompt_override')
      interventions.push({ type: item.type, content: item.text })
    else if (item.type === 'model_override')
      interventions.push({ type: item.type, model: item.text })
    else {
      try {
        interventions.push({ type: item.type, parameters: JSON.parse(item.text) })
      } catch {
        return { interventions, error: 'Generation override must be a JSON object.' }
      }
    }
  }
  return { interventions, error: null }
}

export type DiffLine = { op: ' ' | '+' | '-'; text: string }

/** Small line diff for reviewing a replacement; large inputs report counts only. */
export function lineDiff(before: string, after: string, limit = 400): DiffLine[] | null {
  const a = before.split('\n'),
    b = after.split('\n')
  if (a.length > limit || b.length > limit) return null
  const table = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  )
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      table[i][j] =
        a[i] === b[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1])
  const out: DiffLine[] = []
  let i = 0,
    j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ op: ' ', text: a[i] })
      i++
      j++
    } else if (table[i + 1][j] >= table[i][j + 1]) out.push({ op: '-', text: a[i++] })
    else out.push({ op: '+', text: b[j++] })
  }
  while (i < a.length) out.push({ op: '-', text: a[i++] })
  while (j < b.length) out.push({ op: '+', text: b[j++] })
  return out
}

/** Character-based context estimate; TraceLab has no tokenizer for arbitrary providers. */
export const estimateTokens = (characters: number) => Math.ceil(characters / 4)
