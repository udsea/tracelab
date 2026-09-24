import type { ForkExecutionSpec, Intervention, Job } from './domain'
export interface ForkExperimentArm {
  id: string
  name: string
  role: 'control' | 'treatment'
  description?: string
}
export interface ForkExperimentCase {
  id: string
  label?: string
  sourceTrajectoryId: string
  sourceEventId: string
  arms: { armId: string; interventions: Intervention[] }[]
}
export interface ForkExperimentSpec {
  workspaceId: string
  name: string
  description?: string
  arms: ForkExperimentArm[]
  cases: ForkExperimentCase[]
  executionSpec: ForkExecutionSpec
  modelOverrides: {
    provider: string
    model: string
    parameters: Record<string, unknown>
  }
  replicationCount: number
  schedulePolicy: 'paired_interleaved_v1'
}
export type TrialStatus =
  | 'pending'
  | 'running'
  | 'complete'
  | 'error'
  | 'cancelled'
  | 'interrupted'
export interface Progress extends Record<TrialStatus, number> {
  total: number
  finalized: number
}
export interface ForkExperiment extends ForkExperimentSpec {
  id: string
  status:
    | 'configured'
    | 'running'
    | 'complete'
    | 'partial'
    | 'cancelled'
    | 'failed'
  createdAt: string
  jobId?: string
  specHash: string
  metadata: Record<string, unknown>
}
export interface ForkTrial {
  id: string
  experimentId: string
  caseId: string
  armId: string
  forkId: string
  replicationIndex: number
  pairKey: string
  scheduleOrdinal: number
  status: TrialStatus
  childTrajectoryId?: string
  requestedSeed?: number
  error?: string
  metadata: { terminationReason?: string; executionStatus?: string }
}
export interface ExperimentPreview {
  specHash: string
  totalCases: number
  totalArms: number
  replicationCount: number
  totalTrials: number
  allSupported: boolean
  cells: {
    caseId: string
    armId: string
    supported: boolean
    reasonCode?: string
    reason?: string
    inputHash?: string
    executionHash?: string
    contextCharacters?: number
    replayEntryCount?: number
  }[]
}
export interface ExperimentDetail {
  experiment: ForkExperiment
  progress: Progress
  cells: {
    caseId: string
    armId: string
    progress: Progress
    terminationCounts: Record<string, number>
  }[]
  trials: ForkTrial[]
  usage: Record<string, number>
  executionStatusCounts: Record<string, number>
}
export interface ExperimentSummary {
  id: string
  name: string
  status: string
  caseCount: number
  armCount: number
  replicationCount: number
  createdAt: string
  progress: Progress
}
export interface ExperimentStart {
  started: boolean
  experimentId?: string
  job?: Job
  preview?: ExperimentPreview
}
