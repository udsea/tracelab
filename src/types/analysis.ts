import type {
  Metadata,
  EventPresentationClass,
  ReasoningVisibility,
  EventCounts,
} from './domain'
export interface AnalysisSignal {
  id: string
  trajectoryId: string
  name: string
  sourceType: string
  channel: 'BLACK_BOX' | 'GRAY_BOX' | 'WHITE_BOX'
  startEventIndex: number
  endEventIndex: number
  score: number | null
  label: string | null
  evidenceEventIds: string[]
  artifactRef: string | null
  provenance: Metadata
  metadata: Metadata
}
export interface ArtifactRef {
  id: string
  trajectoryId: string
  uri: string
  format: string
  metadata: Metadata
}
export interface OutlineNode {
  id: string
  kind: 'segment' | 'episode' | 'activity' | 'moment'
  label: string
  startEventIndex: number
  endEventIndex: number
  evidenceEventIds: string[]
  stats: {
    eventCount: number
    eventBasis?: string
    durationMs: number | null
    toolCalls: number
    errors: number
    agents: string[]
    filesReferenced: string[]
  }
  provenance: Metadata
}
export interface CoordinatePoint {
  id: string
  index: number
  elapsedMs: number | null
  modelCall: number
  modelCallBoundary: boolean
  modelCallId?: string | null
  presentationClass?: EventPresentationClass
  reasoningVisibility?: ReasoningVisibility | null
  agent: string | null
  type: string
  tool: string | null
  error: boolean
  artifacts: boolean
  durationMs: number | null
}
export interface Relationship {
  id: string
  kind: string
  sourceEventId: string
  destinationEventId: string
  sourceIndex: number
  destinationIndex: number
  sourceAgent: string
  destinationAgent: string
  description: string
}
export interface Overview {
  eventCounts: EventCounts
  coordinates: {
    points: CoordinatePoint[]
    missingTimestamps: number
    modelCallFidelity: string
  }
  outline: OutlineNode[]
  relationships: Relationship[]
  analysisCapabilities: Record<string, boolean>
  artifacts: ArtifactRef[]
}
export interface DetectorDefinition {
  id: string
  name: string
  detectorType: 'rule' | 'statistical' | 'contrastive'
  version: number
  parameters: Metadata
}
