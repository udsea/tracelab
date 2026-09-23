import { invoke, isTauri } from '@tauri-apps/api/core'

export async function rpc<T>(method: string, params: object = {}): Promise<T> {
  if (isTauri()) return invoke<T>('rpc', { method, params })
  const response = await fetch('/api/rpc', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method, params }),
  })
  const envelope = await response.json()
  if (envelope.error) throw new Error(envelope.error.message)
  if (!response.ok) throw new Error(`Backend returned ${response.status}`)
  return envelope.result as T
}

export async function chooseLogs(directory = false): Promise<string | null> {
  if (!isTauri()) return null
  const { open } = await import('@tauri-apps/plugin-dialog')
  return open({
    directory,
    multiple: false,
    filters: directory
      ? undefined
      : [{ name: 'Trajectory source', extensions: ['eval', 'json', 'jsonl', 'ndjson'] }],
  })
}

export async function openNative(url: string) {
  if (isTauri()) {
    const { openUrl } = await import('@tauri-apps/plugin-opener')
    await openUrl(url)
  } else window.open(url, '_blank', 'noopener,noreferrer')
}
