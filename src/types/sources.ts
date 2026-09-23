export interface SourceRef {
  kind: 'local' | 'huggingface' | 'http'
  uri: string
  revision?: string | null
  sizeBytes?: number | null
  etag?: string | null
  checksum?: string | null
  metadata: Record<string, unknown>
}
export interface SourceEntry {
  ref: SourceRef
  name: string
  path?: string
  isDirectory: boolean
  sizeBytes?: number | null
  formatHint?: string | null
  cachedBytes?: number
}
export interface Detection {
  confidence: number
  format: string
  reason: string
}
export interface SourceDetection {
  ref: SourceRef
  detections: Detection[]
  mapping?: Record<string, string>
  fingerprint?: string
  knownProfile?: boolean
  sample?: unknown
  schema?: unknown
}
export interface Capabilities {
  analyze: boolean
  classify: boolean
  segment: boolean
  visualize: boolean
  multiAgentGraph: boolean
  artifacts: boolean
  contextFork: boolean
  checkpointFork: boolean
  environmentFork: boolean
  exactReplay: boolean
  reason: string
}
export interface CacheStats {
  usageBytes: number
  pinnedBytes: number
  maximumBytes: number
  categories: Record<string, number>
  transferredBytes: number
  requests: number
}
export function bytes(value?: number | null): string {
  if (value == null) return 'Unknown size'
  if (value < 1024) return `${value} B`
  const unit = Math.min(3, Math.floor(Math.log(value) / Math.log(1024)))
  return `${(value / 1024 ** unit).toFixed(1)} ${['B', 'KiB', 'MiB', 'GiB'][unit]}`
}
