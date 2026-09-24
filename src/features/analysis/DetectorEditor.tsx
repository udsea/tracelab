import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useUI, notify } from '@/stores/ui'
import { rpc } from '@/lib/api'
import type { DetectorDefinition } from '@/types/analysis'
import type { Metadata } from '@/types/domain'
export function DetectorEditor({ kind }: { kind: 'rule' | 'statistical' }) {
  const ui = useUI(),
    client = useQueryClient(),
    [name, setName] = useState('Evaluator-file access'),
    [selected, setSelected] = useState<string | null>(null)
  const [parameters, setParameters] = useState<Metadata>({
    operation: 'match',
    eventTypes: ['tool_call'],
    contains: ['grader', 'evaluator', 'hidden_test', 'benchmark'],
    label: 'evaluator_related_access',
  })
  const [windowSize, setWindow] = useState(30),
    [sensitivity, setSensitivity] = useState('medium'),
    [features, setFeatures] = useState(['tool', 'event', 'error', 'agent'])
  const query = useQuery({
    queryKey: ['detectors'],
    queryFn: () =>
      rpc<{
        definitions: DetectorDefinition[]
        templates: Record<string, Metadata>
      }>('analysis.definitions'),
  })
  const save = useMutation({
    mutationFn: async (run: boolean) => {
      const definition = await rpc<DetectorDefinition>('analysis.save', {
        ...(selected ? { id: selected } : {}),
        name:
          kind === 'statistical' && name === 'Evaluator-file access'
            ? 'Behavioral statistics'
            : name,
        detectorType: kind,
        parameters:
          kind === 'rule'
            ? parameters
            : { window: windowSize, sensitivity, features },
      })
      setSelected(definition.id)
      await client.invalidateQueries({ queryKey: ['detectors'] })
      if (run)
        await rpc('analysis.run', {
          definitionId: definition.id,
          trajectoryIds: [ui.trajectoryId],
        })
      await client.invalidateQueries({ queryKey: ['jobs'] })
      notify(run ? 'Analysis job started' : 'Detector version saved')
    },
    onError: (e: Error) => notify(e.message),
  })
  const change = (key: string, value: unknown) =>
    setParameters((p) => ({ ...p, [key]: value }))
  return (
    <div className="feature-page">
      <h2>{kind === 'rule' ? 'Rule detector' : 'Statistical detector'}</h2>
      <p>
        Research heuristic · not validated ground truth. Saved edits create a
        new immutable version.
      </p>
      <div className="analysis-presets">
        {kind === 'rule' &&
          Object.entries(query.data?.templates ?? {}).map(([id, p]) => (
            <button
              key={id}
              onClick={() => {
                setSelected(null)
                setName(String(p.name))
                setParameters(p)
              }}
            >
              {String(p.name)}
            </button>
          ))}
        {query.data?.definitions
          .filter((d) => d.detectorType === kind)
          .map((d) => (
            <button
              key={d.id}
              onClick={() => {
                setSelected(d.id)
                setName(d.name)
                setParameters(d.parameters)
                setWindow(Number(d.parameters.window ?? 30))
                setSensitivity(String(d.parameters.sensitivity ?? 'medium'))
                setFeatures(
                  (d.parameters.features as string[]) ?? [
                    'tool',
                    'event',
                    'error',
                    'agent',
                  ],
                )
              }}
            >
              {d.name} v{d.version}
            </button>
          ))}
      </div>
      <label className="field">
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {kind === 'rule' ? (
        <>
          {['eventTypes', 'tools', 'contains'].map((key) => (
            <label className="field" key={key}>
              {key} · separate with |
              <input
                value={((parameters[key] as string[]) ?? []).join(' | ')}
                onChange={(e) =>
                  change(
                    key,
                    e.target.value
                      .split('|')
                      .map((v) => v.trim())
                      .filter(Boolean),
                  )
                }
              />
            </label>
          ))}
          <label className="field">
            Output label
            <input
              value={String(parameters.label ?? 'rule_match')}
              onChange={(e) => change('label', e.target.value)}
            />
          </label>
          <details>
            <summary>Exact rule definition</summary>
            <pre>{JSON.stringify(parameters, null, 2)}</pre>
          </details>
        </>
      ) : (
        <>
          <label className="field">
            Window (events)
            <input
              type="number"
              min={3}
              max={500}
              value={windowSize}
              onChange={(e) => setWindow(Number(e.target.value))}
            />
          </label>
          <label className="field">
            Sensitivity
            <select
              value={sensitivity}
              onChange={(e) => setSensitivity(e.target.value)}
            >
              {['low', 'medium', 'high'].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <div>
            {['tool', 'event', 'error', 'agent'].map((f) => (
              <label key={f}>
                <input
                  type="checkbox"
                  checked={features.includes(f)}
                  onChange={() =>
                    setFeatures(
                      features.includes(f)
                        ? features.filter((x) => x !== f)
                        : [...features, f],
                    )
                  }
                />
                {f}{' '}
              </label>
            ))}
          </div>
          <p>
            Total-variation change candidates, repetition, error fraction, tool
            entropy, action novelty and robust latency/token spikes.
          </p>
        </>
      )}
      <div className="form-actions">
        <button disabled={save.isPending} onClick={() => save.mutate(false)}>
          Save version
        </button>
        <button
          disabled={save.isPending || !ui.trajectoryId}
          onClick={() => save.mutate(true)}
        >
          Save & run on trajectory
        </button>
      </div>
    </div>
  )
}
