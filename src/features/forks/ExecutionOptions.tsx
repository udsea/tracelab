import { Field } from '@/components/common/Primitives'
import { useUI } from '@/stores/ui'
import type { ForkExecutionSpec, Metadata, ToolStub } from '@/types/domain'

export const defaultExecution: ForkExecutionSpec = {
  continuation: 'single_turn',
  toolPolicy: 'disabled',
  environment: 'none',
  scoring: 'none',
  unmatchedToolPolicy: 'fail',
  maxModelSteps: 8,
  maxToolCalls: 32,
  toolStubs: [],
}
export interface ReplayPreview {
  replaySupport: {
    supported: boolean
    reasonCode: string | null
    reason: string
  }
  toolCatalog: { count: number; hash: string; names: string[] } | null
  replayPlan: {
    policy: string
    entryCount: number
    hash: string | null
    entries: {
      ordinal: number
      toolName: string
      sourceCallEventId: string
      sourceResultEventId: string
    }[]
  }
}
export function parseStubs(text: string): {
  stubs: ToolStub[]
  error?: string
} {
  try {
    const value: unknown = JSON.parse(text)
    if (
      !Array.isArray(value) ||
      value.some(
        (s) =>
          !s ||
          typeof s !== 'object' ||
          !s.id ||
          !s.toolName ||
          !('arguments' in s),
      )
    )
      throw new Error(
        'Each stub needs id, toolName, arguments, and a result or structured error.',
      )
    return { stubs: value as ToolStub[] }
  } catch (error) {
    return { stubs: [], error: `Invalid exact stubs: ${String(error)}` }
  }
}
export function ExecutionOptions({
  value,
  onChange,
  stubs,
  onStubs,
}: {
  value: ForkExecutionSpec
  onChange: (value: ForkExecutionSpec) => void
  stubs: string
  onStubs: (value: string) => void
}) {
  const multi = value.continuation === 'multi_step'
  return (
    <>
      <Field label="Mode">
        <select
          aria-label="Continuation mode"
          value={value.continuation}
          onChange={(e) =>
            onChange(
              e.target.value === 'multi_step'
                ? {
                    ...value,
                    continuation: 'multi_step',
                    toolPolicy: 'recorded_replay',
                  }
                : { ...defaultExecution },
            )
          }
        >
          <option value="single_turn">Single reply</option>
          <option value="multi_step">Multi-step recorded replay</option>
        </select>
      </Field>
      {multi && (
        <>
          <span className="tag">RECORDED TOOL REPLAY</span>
          <p className="muted">
            The model may continue through multiple tool calls. TraceLab only
            returns the next exact recorded tool result. Tools are not executed
            and environment state is not restored.
          </p>
          <div className="form-row">
            <Field label="Max model steps">
              <input
                aria-label="Max model steps"
                type="number"
                min={1}
                max={100}
                value={value.maxModelSteps}
                onChange={(e) =>
                  onChange({ ...value, maxModelSteps: +e.target.value })
                }
              />
            </Field>
            <Field label="Max tool calls">
              <input
                aria-label="Max tool calls"
                type="number"
                min={1}
                max={1000}
                value={value.maxToolCalls}
                onChange={(e) =>
                  onChange({ ...value, maxToolCalls: +e.target.value })
                }
              />
            </Field>
            <Field label="Unmatched tool call">
              <select
                aria-label="Unmatched tool policy"
                value={value.unmatchedToolPolicy}
                onChange={(e) =>
                  onChange({
                    ...value,
                    unmatchedToolPolicy: e.target.value as 'fail' | 'stub',
                  })
                }
              >
                <option value="fail">Stop replay</option>
                <option value="stub">Try exact researcher stubs</option>
              </select>
            </Field>
          </div>
          {value.unmatchedToolPolicy === 'stub' && (
            <Field
              label="Exact stubs (JSON)"
              hint="Synthetic observations. Each needs id, toolName, exact arguments, result and optional structured error. After the first stub, recorded replay cannot resume."
            >
              <textarea
                aria-label="Exact stubs"
                className="mono"
                rows={5}
                value={stubs}
                onChange={(e) => onStubs(e.target.value)}
              />
            </Field>
          )}
        </>
      )}
    </>
  )
}
export function ReplaySummary({ preview }: { preview?: ReplayPreview }) {
  if (!preview) return <p className="muted">Preparing replay plan…</p>
  return (
    <div className="fidelity-panel">
      {!preview.replaySupport.supported && (
        <div className="inline-error">
          Recorded replay unavailable: {preview.replaySupport.reason} (
          {preview.replaySupport.reasonCode})
        </div>
      )}
      {preview.toolCatalog && (
        <p>
          {preview.toolCatalog.count} explicit tool schemas:{' '}
          {preview.toolCatalog.names.join(', ')}
        </p>
      )}
      <p>
        {preview.replayPlan.entryCount} sequential recorded observations ·{' '}
        {preview.replayPlan.policy}
      </p>
      <ol>
        {preview.replayPlan.entries.map((e) => (
          <li key={e.ordinal}>
            {e.toolName} · {e.sourceCallEventId} → {e.sourceResultEventId}
          </li>
        ))}
      </ol>
      <details>
        <summary>Replay plan hash</summary>
        <code>{preview.replayPlan.hash ?? 'Unavailable'}</code>
      </details>
    </div>
  )
}
const reasons: Record<string, string> = {
  assistant_completed: 'Assistant completed',
  unmatched_tool_call: 'Stopped at unmatched tool call',
  replay_tape_exhausted: 'Recorded observations exhausted',
  max_model_steps: 'Model-step limit reached',
  max_tool_calls: 'Tool-call limit reached',
  cancelled: 'Cancelled',
  model_error: 'Model execution error',
  unsupported_tool_result: 'Unsupported recorded result',
  tool_resolution_error: 'Tool resolution error',
}
export function ExecutionSummary({ metadata }: { metadata?: Metadata }) {
  if (metadata?.executionMode !== 'multi_step_recorded_replay') return null
  return (
    <span className="muted">
      Multi-step recorded replay · {Number(metadata.modelSteps ?? 0)} model
      calls · {Number(metadata.replayedToolCalls ?? 0)} replayed ·{' '}
      {Number(metadata.stubbedToolCalls ?? 0)} stubbed
      <br />
      {reasons[String(metadata.terminationReason)] ?? 'Running'}
      {metadata.replayState === 'diverged_by_stub' &&
        ' · Replay diverged after stub'}
    </span>
  )
}
export function ToolOrigin({ metadata }: { metadata: Metadata }) {
  const ui = useUI()
  if (metadata.toolResultOrigin === 'stub')
    return (
      <div className="fidelity-panel">
        <span className="tag">STUBBED</span>
        <p>
          Researcher-supplied synthetic result · stub {String(metadata.stubId)}
        </p>
        <p>Recorded replay cannot resume after this observation.</p>
      </div>
    )
  if (metadata.toolResultOrigin !== 'recorded_replay') return null
  return (
    <div className="fidelity-panel">
      <span className="tag">RECORDED REPLAY</span>
      <p>Recorded observation; tool not executed. Environment not restored.</p>
      <code>{String(metadata.matchPolicy)}</code>
      <p>
        {['Call', 'Result'].map((kind) => (
          <button
            className="link"
            key={kind}
            onClick={() => {
              ui.selectTrajectory(String(metadata.matchedSourceTrajectoryId))
              ui.jump(Number(metadata[`matchedSource${kind}Index`]))
            }}
          >
            Source {kind.toLowerCase()} #
            {String(metadata[`matchedSource${kind}Index`])}{' '}
          </button>
        ))}
      </p>
    </div>
  )
}
