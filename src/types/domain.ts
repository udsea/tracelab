export type EventPresentationClass = 'semantic' | 'runtime' | 'opaque'
export type ReasoningVisibility =
  | 'plaintext'
  | 'summary'
  | 'encrypted'
  | 'redacted'
  | 'opaque'
export interface EventLocation {
  offset: number | null
  exact: boolean
  eventIndex: number
  nearestEventIndex?: number | null
}
export interface EventCounts {
  recorded: number
  research: number
  semantic: number
  runtime: number
  opaque: number
}
import type { SourceRef, Capabilities } from './sources'
export type Metadata = Record<string, unknown>
export interface Workspace {
  id: string
  name: string
  sources: string[]
  createdAt: string
  openedAt: string
  isDemo: boolean
}
export interface Experiment {
  id: string
  workspaceId: string
  name: string
  sourcePath: string
  sourceType: string
  sourceRef?: SourceRef | null
  trajectoryCount?: number
  task?: string
  dataset?: string
  importedAt: string
  metadata: Metadata
}
export type TrajectoryStatus =
  | 'running'
  | 'success'
  | 'failure'
  | 'error'
  | 'cancelled'
  | 'unknown'
export interface Trajectory {
  id: string
  experimentId: string
  sampleId: string
  epoch?: number
  model?: string
  task?: string
  condition?: string
  status: TrajectoryStatus
  startedAt?: string
  completedAt?: string
  durationMs?: number
  inputTokens?: number
  outputTokens?: number
  totalTokens?: number
  scores: Metadata
  parentTrajectoryId?: string
  forkId?: string
  eventCount: number
  loaded: boolean
  sourceRef?: SourceRef | null
  capabilities?: Capabilities | null
  metadata: Metadata
}
export type EventType =
  | 'system'
  | 'user'
  | 'assistant'
  | 'reasoning'
  | 'tool_call'
  | 'tool_result'
  | 'environment'
  | 'score'
  | 'error'
  | 'checkpoint'
  | 'annotation'
  | 'other'
export interface ToolData {
  name: string
  callId?: string
  arguments?: unknown
  result?: unknown
  error?: string
}
export interface TrajectoryEvent {
  id: string
  trajectoryId: string
  index: number
  parentEventIds: string[]
  timestamp?: string
  type: EventType
  role?: string
  content?: string
  tool?: ToolData
  tokenUsage?: { input?: number; output?: number }
  metadata: Metadata
}
export interface EventSummary {
  id: string
  trajectoryId: string
  index: number
  type: EventType
  role?: string
  preview: string
  timestamp?: string
  toolName?: string
  hasError: boolean
  tokenUsage?: { input?: number; output?: number }
  intervened?: boolean
  presentationClass?: EventPresentationClass
  reasoningVisibility?: ReasoningVisibility | null
}
export interface Segment {
  id: string
  trajectoryId: string
  startEvent: number
  endEvent: number
  label: string
  summary: string
  confidence?: number
  parentId?: string
  provenance: Metadata
}
export interface Annotation {
  id: string
  trajectoryId: string
  startEventIndex: number
  endEventIndex: number
  label: string
  note?: string
  createdAt: string
}
export interface ClassifierDefinition {
  version?: number
  previousId?: string | null
  id: string
  workspaceId?: string | null
  name: string
  description: string
  prompt: string
  model: string
  provider: string
  scope: 'event' | 'window' | 'trajectory'
  windowSize: number
  stride: number
  labels: string[]
  returnScore: boolean
  returnRationale: boolean
  returnEvidence: boolean
  outputSchema: Metadata
  generationParameters: Metadata
  createdAt: string
  isTemplate: boolean
}
export interface ClassifierOutput {
  label?: string
  score?: number
  rationale?: string
  evidenceEventIds: string[]
}
export interface ClassifierResult {
  id: string
  classifierId: string
  runId: string
  trajectoryId: string
  startEventIndex: number
  endEventIndex: number
  output?: ClassifierOutput
  error?: string
  cacheKey: string
  cached: boolean
  createdAt: string
  provenance?: Metadata
}
export type Intervention =
  | { type: 'remove_event'; eventId: string }
  | { type: 'replace_content'; eventId: string; content: string }
  | { type: 'replace_tool_result'; eventId: string; value: unknown }
  | { type: 'append_message'; role: string; content: string }
  | { type: 'system_prompt_override'; content: string }
  | { type: 'model_override'; model: string }
  | { type: 'generation_override'; parameters: Metadata }
export interface Fork {
  id: string
  sourceTrajectoryId: string
  sourceEventId: string
  createdAt: string
  fidelity: 'context_only' | 'checkpoint_restored'
  interventions: Intervention[]
  modelOverrides: Metadata
  replicationCount: number
  childTrajectoryIds: string[]
  status: 'configured' | 'running' | 'complete' | 'failed'
  metadata: Metadata
}
export interface Job {
  id: string
  kind: 'import' | 'classifier' | 'fork' | 'segmentation' | 'index' | 'analysis'
  name: string
  status: 'queued' | 'running' | 'complete' | 'failed' | 'cancelled'
  completed: number
  total: number
  concurrency: number
  createdAt: string
  completedAt?: string
  error?: string
  logs: string[]
  metadata: Metadata
}
export interface Provider {
  id: string
  name: string
  kind: 'openai_compatible' | 'anthropic'
  baseUrl: string
  apiKeyEnv: string
  defaultModel: string
  configured?: boolean
}
export interface TimelineData {
  markers: {
    id: string
    index: number
    type: EventType
    tool?: string
    error: boolean
    usage?: string
    agent?: string | null
  }[]
  segments: Segment[]
  annotations: Annotation[]
  checkpoints: { id: string; index: number; restorable: boolean }[]
  forks: Fork[]
  results: ClassifierResult[]
}
export interface Page<T> {
  items: T[]
  total: number
  offset?: number
}
export interface Filter {
  field: string
  op: string
  value: string | number
  key?: string
}
export interface SearchHit {
  id: string
  trajectoryId: string
  index: number
  type: string
  preview: string
}
export interface PairComparison {
  left: Trajectory
  right: Trajectory
  commonPrefix: number
  interventionIndex?: number
  firstBehaviouralDivergence?: { left?: number; right?: number }
  method: string
  rows: {
    left?: Pick<EventSummary, 'id' | 'index' | 'type' | 'preview' | 'toolName'>
    right?: Pick<EventSummary, 'id' | 'index' | 'type' | 'preview' | 'toolName'>
    changed: boolean
    intervention: boolean
    similarity?: number
  }[]
}
