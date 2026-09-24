import type { AnalysisSignal } from '@/types/analysis'

type Channel = AnalysisSignal['channel']

export const channelLabels: Record<Channel, string> = {
  BLACK_BOX: 'Black box',
  GRAY_BOX: 'Gray box',
  WHITE_BOX: 'White box',
}

/** One explanation, shown on request rather than on every selected event. */
export const channelHelp: Record<Channel, string> = {
  BLACK_BOX:
    'Derived from the recorded transcript and tool calls: LLM detectors, rules, statistics and annotations.',
  GRAY_BOX:
    'Recorded environment observations, such as sandbox commands and file writes.',
  WHITE_BOX:
    'Imported model-internal measurements (probes, SAE features, logits). TraceLab does not instrument models itself.',
}

export const sourceLabels: Record<string, string> = {
  llm: 'Semantic · LLM',
  rule: 'Rule',
  statistical: 'Statistical',
  contrastive: 'Contrastive',
  environment: 'Environment',
  human: 'Human',
  intervention: 'Intervention',
  probe: 'Imported probe',
  sae: 'Imported SAE',
  logit: 'Imported logits',
  custom: 'Imported measurement',
}

export const sourceLabel = (sourceType: string) =>
  sourceLabels[sourceType] ?? sourceType
