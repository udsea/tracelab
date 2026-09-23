import { useState } from 'react'
import { rpc } from '@/lib/api'
import {
  ArrowUpRight,
  Check,
  FlaskConical,
  Info,
  Play,
  Plus,
  Save,
  SlidersHorizontal,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TrajectorySelection } from '@/components/trajectory/TrajectoryPicker'
import { Field, Loading } from '@/components/common/Primitives'
import {
  useAction,
  useClassifiers,
  useProviders,
  useTrajectory,
} from '@/hooks/queries'
import { notify, useUI } from '@/stores/ui'
import type { ClassifierDefinition, Job } from '@/types/domain'
const blank = (): ClassifierDefinition => ({
  id: crypto.randomUUID(),
  name: '',
  description: '',
  prompt: '',
  model: '',
  provider: 'openai',
  scope: 'window',
  windowSize: 20,
  stride: 5,
  labels: [],
  returnScore: true,
  returnRationale: true,
  returnEvidence: true,
  outputSchema: {},
  generationParameters: {},
  createdAt: new Date().toISOString(),
  isTemplate: false,
})
export function ClassifierWorkspace() {
  const ui = useUI()
  const definitions = useClassifiers()
  const [editing, setEditing] = useState<ClassifierDefinition | null>(null)
  return (
    <div className="feature-page classifier-page">
      <div className="feature-heading">
        <div>
          <span className="eyebrow">ANALYSIS WORKBENCH</span>
          <h1>Classifiers</h1>
          <p>Turn research questions into signals you can inspect.</p>
        </div>
        <Button onClick={() => setEditing(blank())}>
          <Plus size={14} />
          New classifier
        </Button>
      </div>
      <div className="classifier-layout">
        <div className="classifier-library">
          <div className="section-label">YOUR CLASSIFIERS</div>
          {definitions.isLoading && <Loading />}
          {definitions.data
            ?.filter((d) => !d.isTemplate)
            .map((d) => (
              <button
                className={`classifier-library-item ${editing?.id === d.id ? 'active' : ''}`}
                onClick={() => setEditing(d)}
                key={d.id}
              >
                <FlaskConical size={16} />
                <span>
                  <strong>{d.name}</strong>
                  <small>
                    {d.scope} · {d.model || 'No model selected'}
                  </small>
                </span>
                <ArrowUpRight size={12} />
              </button>
            ))}
          <div className="section-label template-heading">
            EDITABLE TEMPLATES
            <span>
              {
                definitions.data?.filter(
                  (d) => d.isTemplate && !d.id.startsWith('demo'),
                ).length
              }
            </span>
          </div>
          {definitions.data
            ?.filter((d) => d.isTemplate && !d.id.startsWith('demo'))
            .map((d) => (
              <button
                className={`classifier-library-item ${editing?.id === d.id ? 'active' : ''}`}
                onClick={() => setEditing({ ...d })}
                key={d.id}
              >
                <div className="classifier-template-icon">
                  <FlaskConical size={14} />
                </div>
                <span>
                  <strong>{d.name}</strong>
                  <small>
                    {d.scope === 'window' ? 'Rolling window' : d.scope}
                  </small>
                </span>
                <span className="template-dot" />
              </button>
            ))}
          <div className="library-note">
            <Info size={15} />
            <p>
              Templates are starting points, not validated safety detectors.
              Inspect and adapt every prompt.
            </p>
          </div>
        </div>
        <div className="classifier-editor">
          {editing ? (
            <ClassifierEditor
              key={editing.id}
              definition={editing}
              onSaved={setEditing}
            />
          ) : (
            <div className="classifier-intro">
              <div className="intro-glyph">
                <FlaskConical size={30} />
              </div>
              <h2>
                A signal is only useful
                <br />
                when you can trace its evidence.
              </h2>
              <p>
                Start with an editable template or define your own question.
                Every result includes the input events, exact prompt, raw
                response, and model configuration.
              </p>
              <div className="classifier-example">
                <div>
                  <span className="green-dot" />
                  EVALUATION AWARENESS<span>EXAMPLE FORMAT</span>
                </div>
                <pre>
                  {
                    '{\n  "label": "probable",\n  "score": 0.84,\n  "rationale": "…",\n  "evidence_event_ids": ["…"]\n}'
                  }
                </pre>
              </div>
              <Button variant="outline" onClick={() => setEditing(blank())}>
                <Plus size={14} />
                Create a classifier
              </Button>
              <button
                className="text-link"
                onClick={() => ui.set({ modal: 'settings' })}
              >
                Configure model providers
                <ArrowUpRight size={12} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
function ClassifierEditor({
  definition,
  onSaved,
}: {
  definition: ClassifierDefinition
  onSaved: (d: ClassifierDefinition) => void
}) {
  const ui = useUI()
  const providers = useProviders()
  const trajectory = useTrajectory(ui.trajectoryId)
  const [form, setForm] = useState(definition)
  const [labels, setLabels] = useState(definition.labels.join(', '))
  const [parameters, setParameters] = useState(
    JSON.stringify(definition.generationParameters),
  )
  const [schema, setSchema] = useState(
    Object.keys(definition.outputSchema).length
      ? JSON.stringify(definition.outputSchema, null, 2)
      : '',
  )
  const [target, setTarget] = useState('trajectory')
  const [selected, setSelected] = useState<string[]>(
    ui.trajectoryId ? [ui.trajectoryId] : [],
  )
  const [concurrency, setConcurrency] = useState(4)
  const [rerun, setRerun] = useState(false)
  const save = useAction<ClassifierDefinition>('classifiers.save', [
    'classifiers',
  ])
  const run = useAction<Job>('classifiers.run', ['jobs'])
  function update(value: Partial<ClassifierDefinition>) {
    setForm((f) => ({ ...f, ...value }))
  }
  async function submit(launch: boolean) {
    try {
      const item = {
        ...form,
        workspaceId: ui.workspaceId,
        id: form.isTemplate ? crypto.randomUUID() : form.id,
        isTemplate: false,
        labels: labels
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        generationParameters: JSON.parse(parameters || '{}'),
        outputSchema: JSON.parse(schema || '{}'),
      }
      const saved = await save.mutateAsync(item)
      onSaved(saved)
      if (launch) {
        const scope =
          target === 'workspace'
            ? { workspaceId: ui.workspaceId }
            : target === 'experiment'
              ? {
                  experimentId: trajectory.data?.trajectory.experimentId,
                  workspaceId: ui.workspaceId,
                }
              : target === 'condition'
                ? {
                    workspaceId: ui.workspaceId,
                    filters: [
                      {
                        field: 'condition',
                        op: 'eq',
                        value: trajectory.data?.trajectory.condition,
                      },
                    ],
                  }
                : {
                    trajectoryIds:
                      target === 'selected'
                        ? selected
                        : ui.trajectoryId
                          ? [ui.trajectoryId]
                          : [],
                  }
        await run.mutateAsync({
          classifierId: saved.id,
          ...scope,
          concurrency,
          rerun,
          ...(target === 'event'
            ? { eventIds: [(await rpc<{event:{id:string}}>('events.get', {trajectoryId: ui.trajectoryId, index: ui.selectedIndex})).event.id] }
            : {}),
        })
        ui.set({ modal: 'jobs' })
      } else notify('Classifier saved')
    } catch (error) {
      notify(String(error))
    }
  }
  return (
    <div className="editor-form">
      <div className="editor-heading">
        <FlaskConical size={17} />
        <h3>
          {form.isTemplate ? 'Customize template' : 'Classifier definition'}
        </h3>
        {form.isTemplate && <span className="tag">TEMPLATE</span>}
      </div>
      <Field label="Name">
        <input
          value={form.name}
          placeholder="e.g. Evaluation awareness"
          onChange={(e) => update({ name: e.target.value })}
        />
      </Field>
      <Field label="Description">
        <input
          value={form.description}
          placeholder="What question does this classifier answer?"
          onChange={(e) => update({ description: e.target.value })}
        />
      </Field>
      <Field
        label="Classifier prompt"
        hint="Events are supplied as structured research data. Evidence must refer to the supplied event IDs."
      >
        <textarea
          className="prompt-editor"
          rows={5}
          value={form.prompt}
          onChange={(e) => update({ prompt: e.target.value })}
        />
      </Field>
      <div className="form-row">
        <Field label="Scope">
          <select
            value={form.scope}
            onChange={(e) =>
              update({ scope: e.target.value as ClassifierDefinition['scope'] })
            }
          >
            <option value="event">Event</option>
            <option value="window">Rolling window</option>
            <option value="trajectory">Full trajectory</option>
          </select>
        </Field>
        {form.scope === 'window' && (
          <>
            <Field label="Window size">
              <input
                type="number"
                min={1}
                value={form.windowSize}
                onChange={(e) => update({ windowSize: +e.target.value })}
              />
            </Field>
            <Field label="Stride">
              <input
                type="number"
                min={1}
                value={form.stride}
                onChange={(e) => update({ stride: +e.target.value })}
              />
            </Field>
          </>
        )}
      </div>
      <div className="form-row">
        <Field label="Provider">
          <select
            value={form.provider}
            onChange={(e) =>
              update({
                provider: e.target.value,
                model:
                  providers.data?.find((p) => p.id === e.target.value)
                    ?.defaultModel || form.model,
              })
            }
          >
            {providers.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.configured ? '' : ' · key not set'}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Model">
          <input
            value={form.model}
            placeholder="provider model ID"
            onChange={(e) => update({ model: e.target.value })}
          />
        </Field>
      </div>
      <Field
        label="Labels"
        hint="Comma-separated. Leave empty for a numeric signal only."
      >
        <input value={labels} onChange={(e) => setLabels(e.target.value)} />
      </Field>
      <div className="return-fields">
        <span>Return</span>
        {(['returnScore', 'returnRationale', 'returnEvidence'] as const).map(
          (key, i) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={form[key]}
                onChange={(e) => update({ [key]: e.target.checked })}
              />
              {['Score', 'Rationale', 'Evidence events'][i]}
            </label>
          ),
        )}
      </div>
      <details className="advanced-fields">
        <summary>
          <SlidersHorizontal size={13} />
          Structured schema & generation parameters
        </summary>
        <Field label="Generation parameters (JSON)">
          <textarea
            rows={2}
            value={parameters}
            onChange={(e) => setParameters(e.target.value)}
          />
        </Field>
        <Field
          label="Custom output schema (optional JSON)"
          hint="Keep the standard label, score, rationale and evidence_event_ids fields. Empty uses a strict generated schema."
        >
          <textarea
            rows={4}
            value={schema}
            onChange={(e) => setSchema(e.target.value)}
          />
        </Field>
      </details>
      <div className="run-settings">
        <div className="form-row">
          <Field label="Run against">
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="trajectory">Current trajectory</option>
              <option value="event">Selected event #{ui.selectedIndex}</option>
              <option value="selected">Selected trajectories</option>
              <option value="experiment">Current experiment</option>
              <option value="condition">Current condition</option>
              <option value="workspace">Entire workspace</option>
            </select>
          </Field>
          <Field label="Concurrency">
            <input
              type="number"
              min={1}
              max={16}
              value={concurrency}
              onChange={(e) => setConcurrency(+e.target.value)}
            />
          </Field>
        </div>
        {target === 'selected' && (
          <TrajectorySelection value={selected} onChange={setSelected} />
        )}
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={rerun}
            onChange={(e) => setRerun(e.target.checked)}
          />
          Rerun identical inputs (bypass cache)
        </label>
        <p className="muted small">
          Running sends the selected event content to your configured provider.
        </p>
      </div>
      <div className="form-actions">
        <span>
          <Check size={12} />
          Structured output · linked evidence
        </span>
        <Button
          variant="outline"
          disabled={!form.name || !form.prompt || save.isPending}
          onClick={() => {
            void submit(false)
          }}
        >
          <Save size={13} />
          Save
        </Button>
        <Button
          disabled={
            !form.name ||
            !form.prompt ||
            !form.model ||
            save.isPending ||
            run.isPending
          }
          onClick={() => {
            void submit(true)
          }}
        >
          <Play size={13} />
          Save & run
        </Button>
      </div>
    </div>
  )
}
