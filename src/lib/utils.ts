import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
export const number = (value?: number | null) =>
  value == null
    ? '—'
    : Intl.NumberFormat('en', {
        maximumFractionDigits: 1,
        notation: value >= 10000 ? 'compact' : 'standard',
      }).format(value)
export const duration = (ms?: number | null) =>
  ms == null
    ? '—'
    : ms > 60000
      ? `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
      : `${(ms / 1000).toFixed(1)}s`
export const eventLabel = (type: string) =>
  ({
    tool_call: 'Tool call',
    tool_result: 'Tool result',
    reasoning: 'Reasoning',
    assistant: 'Assistant',
    environment: 'Environment',
    user: 'User',
    system: 'System',
  })[type] || type[0].toUpperCase() + type.slice(1)
export const json = (value: unknown) => JSON.stringify(value, null, 2)
export const shortModel = (value?: string) =>
  value?.split('/').slice(-1)[0] || 'Model not recorded'
