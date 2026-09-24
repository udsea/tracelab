import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Field } from '@/components/common/Primitives'
import { Button } from '@/components/ui/button'
import { useProviders } from '@/hooks/queries'
import { rpc } from '@/lib/api'
import { useUI } from '@/stores/ui'
import {
  defaultExecution,
  ExecutionOptions,
  parseStubs,
} from '@/features/forks/ExecutionOptions'
import type { TrajectoryEvent } from '@/types/domain'
import type {
  ExperimentPreview,
  ExperimentStart,
  ForkExperimentArm,
  ForkExperimentCase,
  ForkExperimentSpec,
} from '@/types/fork-experiments'

const arms: ForkExperimentArm[] = [
  { id: 'control', name: 'Control', role: 'control' },
  { id: 'treatment', name: 'Treatment', role: 'treatment' },
]
export function trialTotal(cases: number, arms: number, replications: number) {
  return cases * arms * replications
}
export function ExperimentBuilder({
  workspaceId,
  onStarted,
}: {
  workspaceId: string
  onStarted: (id: string) => void
}) {
  const ui = useUI()
  const providers = useProviders()
  const [name, setName] = useState('New fork experiment')
  const [armText, setArms] = useState(JSON.stringify(arms, null, 2))
  const [caseText, setCases] = useState('[]')
  const [replications, setReplications] = useState(1)
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState('')
  const [parameters, setParameters] = useState('{}')
  const [execution, setExecution] = useState(defaultExecution)
  const [stubText, setStubs] = useState('[]')
  const [error, setError] = useState('')
  const [reviewed, setReviewed] = useState<{
    key: string
    value: ExperimentPreview
  }>()
  let spec: ForkExperimentSpec | undefined
  let parseError = ''
  try {
    const cases = JSON.parse(caseText) as ForkExperimentCase[]
    const armList = JSON.parse(armText) as ForkExperimentArm[]
    const params = JSON.parse(parameters) as Record<string, unknown>
    if (
      !Array.isArray(cases) ||
      !Array.isArray(armList) ||
      !params ||
      Array.isArray(params) ||
      typeof params !== 'object'
    )
      throw Error('Cases/arms must be arrays and parameters an object.')
    if (!cases.length || !armList.length)
      throw Error('Add at least one concrete source case and arm.')
    if (
      !Number.isInteger(replications) ||
      replications < 1 ||
      replications > 100 ||
      cases.length > 200 ||
      armList.length > 8 ||
      trialTotal(cases.length, armList.length, replications) > 2000
    )
      throw Error('Limits: 200 cases, 8 arms, 100 replications, 2000 trials.')
    const stubs = parseStubs(stubText)
    if (execution.unmatchedToolPolicy === 'stub' && stubs.error)
      throw Error(stubs.error)
    spec = {
      workspaceId,
      name,
      arms: armList,
      cases,
      replicationCount: replications,
      modelOverrides: { provider, model, parameters: params },
      executionSpec: {
        ...execution,
        toolStubs: execution.unmatchedToolPolicy === 'stub' ? stubs.stubs : [],
      },
      schedulePolicy: 'paired_interleaved_v1',
    }
  } catch (e) {
    parseError = String(e)
  }
  const key = JSON.stringify(spec)
  const preview = useMutation({
    mutationFn: async () => {
      const value = await rpc<ExperimentPreview>(
        'forkExperiments.preview',
        spec,
      )
      setReviewed({ key, value })
    },
    onError: (e) => setError(String(e)),
  })
  const run = useMutation({
    mutationFn: async () => {
      const result = await rpc<ExperimentStart>('forkExperiments.run', {
        ...spec,
        expectedSpecHash: reviewed?.value.specHash,
      })
      if (result.started && result.experimentId) onStarted(result.experimentId)
      else if (result.preview) setReviewed({ key, value: result.preview })
    },
    onError: (e) => setError(String(e)),
  })
  const addSelected = useMutation({
    mutationFn: async () => {
      const { event } = await rpc<{ event: TrajectoryEvent }>('events.get', {
        trajectoryId: ui.trajectoryId,
        index: ui.selectedIndex,
      })
      const cases = JSON.parse(caseText) as ForkExperimentCase[]
      const armList = JSON.parse(armText) as ForkExperimentArm[]
      setCases(
        JSON.stringify(
          [
            ...cases,
            {
              id: `case_${cases.length + 1}`,
              sourceTrajectoryId: event.trajectoryId,
              sourceEventId: event.id,
              arms: armList.map((a) => ({ armId: a.id, interventions: [] })),
            },
          ],
          null,
          2,
        ),
      )
    },
    onError: (e) => setError(String(e)),
  })
  const current = reviewed && reviewed.key === key ? reviewed.value : undefined
  return (
    <div className="fork-form">
      <Field label="Experiment name">
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <p>
        Controls are actual zero-intervention reruns. Historical parent
        trajectories are references, not replicated controls.
      </p>
      <Field label="Arms (JSON)">
        <textarea
          rows={6}
          value={armText}
          onChange={(e) => setArms(e.target.value)}
        />
      </Field>
      <Field
        label="Concrete source cases (JSON)"
        hint="Each case needs id, sourceTrajectoryId, sourceEventId, and arms: [{armId, interventions}]. Use exact event IDs from each source; indices are never mapped across trajectories."
      >
        <textarea
          aria-label="Concrete source cases (JSON)"
          className="mono"
          rows={12}
          value={caseText}
          onChange={(e) => setCases(e.target.value)}
        />
      </Field>
      <Button
        variant="outline"
        disabled={!ui.trajectoryId || addSelected.isPending}
        onClick={() => addSelected.mutate()}
      >
        Add selected event as a case
      </Button>
      <details>
        <summary>Concrete intervention example</summary>
        <pre>
          {JSON.stringify(
            {
              armId: 'treatment',
              interventions: [
                { type: 'remove_event', eventId: 'COPY_EXACT_SOURCE_EVENT_ID' },
              ],
            },
            null,
            2,
          )}
        </pre>
        <p>
          Control defaults to []. For every case, explicitly bind any
          remove/replace target to that case’s own source event.
        </p>
      </details>
      <div className="form-row">
        <Field label="Provider">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            {providers.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Model">
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="Provider model ID"
          />
        </Field>
        <Field label="Replications">
          <input
            type="number"
            min={1}
            max={100}
            value={replications}
            onChange={(e) => setReplications(+e.target.value)}
          />
        </Field>
      </div>
      <Field
        label="Generation parameters (JSON)"
        hint="An explicit seed is incremented per replication and paired across arms unless deliberately overridden. Provider seed support varies."
      >
        <textarea
          rows={2}
          value={parameters}
          onChange={(e) => setParameters(e.target.value)}
        />
      </Field>
      <ExecutionOptions
        value={execution}
        onChange={setExecution}
        stubs={stubText}
        onStubs={setStubs}
      />
      {spec && (
        <p>
          {spec.cases.length} cases × {spec.arms.length} arms × {replications}{' '}
          replications ={' '}
          <strong>
            {trialTotal(spec.cases.length, spec.arms.length, replications)}{' '}
            trials
          </strong>
          . Configured upper bound:{' '}
          {trialTotal(spec.cases.length, spec.arms.length, replications) *
            (execution.continuation === 'multi_step'
              ? execution.maxModelSteps
              : 1)}{' '}
          model calls. Monetary cost unavailable; context is sent to the
          selected provider.
        </p>
      )}
      {(error || parseError) && (
        <p className="inline-error">{error || parseError}</p>
      )}
      <Button
        variant="outline"
        disabled={!spec || !model || preview.isPending || run.isPending}
        onClick={() => {
          setError('')
          preview.mutate()
        }}
      >
        Validate all cells
      </Button>
      {current && (
        <div>
          <p>
            {current.cells.filter((c) => c.supported).length} /{' '}
            {current.cells.length} case-arm cells supported
          </p>
          {current.cells.map((c) => (
            <div key={`${c.caseId}:${c.armId}`}>
              <strong>
                {c.caseId} / {c.armId}
              </strong>{' '}
              · {c.supported ? 'Supported' : `${c.reasonCode}: ${c.reason}`}{' '}
              {c.supported &&
                `· ${c.contextCharacters} context characters · ${c.replayEntryCount} replay entries`}
            </div>
          ))}
        </div>
      )}
      <Button
        disabled={
          !current?.allSupported || preview.isPending || run.isPending || !model
        }
        onClick={() => run.mutate()}
      >
        Run experiment
      </Button>
    </div>
  )
}
