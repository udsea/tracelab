import { describe, expect, it } from 'vitest'
import type { TrajectoryEvent } from '@/types/domain'
import {
  buildGenerationParameters,
  defaultGeneration,
  defaultIntervention,
  lineDiff,
  toInterventions,
} from './request'

const event = (over: Partial<TrajectoryEvent>): TrajectoryEvent => ({
  id: 't:e214',
  trajectoryId: 't',
  index: 214,
  parentEventIds: [],
  type: 'reasoning',
  content: 'original reasoning',
  metadata: {},
  ...over,
})

describe('fork generation parameters', () => {
  it('serializes common fields and omits blanks', () => {
    expect(buildGenerationParameters(defaultGeneration)).toEqual({
      parameters: { max_tokens: 2048 },
      error: null,
    })
    expect(
      buildGenerationParameters({
        temperature: '0.7',
        maxTokens: '512',
        seed: '42',
        advanced: '{"top_p": 0.9, "stop_seqs": ["END"]}',
      }),
    ).toEqual({
      parameters: {
        temperature: 0.7,
        max_tokens: 512,
        seed: 42,
        top_p: 0.9,
        stop_seqs: ['END'],
      },
      error: null,
    })
  })

  it('rejects unsupported and duplicated parameters instead of sending them', () => {
    expect(
      buildGenerationParameters({ ...defaultGeneration, advanced: '{"logit_bias": {}}' })
        .error,
    ).toMatch(/Unsupported parameter "logit_bias"/)
    expect(
      buildGenerationParameters({ ...defaultGeneration, advanced: '{"seed": 1}' }).error,
    ).toMatch(/Set seed with its field/)
    expect(
      buildGenerationParameters({ ...defaultGeneration, temperature: 'hot' }).error,
    ).toMatch(/Temperature/)
    expect(
      buildGenerationParameters({ ...defaultGeneration, seed: '1.5' }).error,
    ).toMatch(/Seed/)
  })
})

describe('fork interventions', () => {
  it('default to replacing the selected event with its original content', () => {
    expect(defaultIntervention(event({}), 214)).toMatchObject({
      type: 'replace_content',
      targetIndex: 214,
      text: 'original reasoning',
      original: 'original reasoning',
    })
  })

  it('prefill structured tool results as JSON and fall back when text is not editable', () => {
    const result = event({
      type: 'tool_result',
      content: '{"ok":true}',
      tool: { name: 'bash', result: { ok: true } },
    })
    expect(defaultIntervention(result, 9)).toMatchObject({
      type: 'replace_tool_result',
      text: '{\n  "ok": true\n}',
    })
    expect(
      defaultIntervention(event({ type: 'tool_call', tool: { name: 'bash' } }), 3).type,
    ).toBe('append_message')
    expect(
      defaultIntervention(
        event({ metadata: { contentBlock: { signature: 'sig' } } }),
        3,
      ).type,
    ).toBe('append_message')
  })

  it('address targets by canonical event id', () => {
    const { interventions, error } = toInterventions('t', [
      { key: 0, type: 'replace_content', targetIndex: 214, text: 'new', original: 'old', role: 'user' },
      { key: 1, type: 'append_message', targetIndex: 214, text: 'note', original: null, role: 'user' },
    ])
    expect(error).toBeNull()
    expect(interventions).toEqual([
      { type: 'replace_content', eventId: 't:e214', content: 'new' },
      { type: 'append_message', role: 'user', content: 'note' },
    ])
    expect(
      toInterventions('t', [
        { key: 0, type: 'replace_tool_result', targetIndex: 2, text: 'not json', original: '', role: 'user' },
      ]).error,
    ).toMatch(/valid JSON/)
  })

  it('diffs replacements line by line', () => {
    expect(lineDiff('a\nb\nc', 'a\nB\nc')).toEqual([
      { op: ' ', text: 'a' },
      { op: '-', text: 'b' },
      { op: '+', text: 'B' },
      { op: ' ', text: 'c' },
    ])
  })
})
