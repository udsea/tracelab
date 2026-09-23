import { useState } from 'react'
import { Check, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/common/Primitives'
import { useAction, useProviders } from '@/hooks/queries'
import type { SourceDetection } from '@/types/sources'

export interface MappingApproval {
  fingerprint: string
  mapping: Record<string, string>
  name: string
  assistance?: unknown
}

export function MappingReview({
  detection,
  approved,
  onApprove,
  onInvalidate,
}: {
  detection: SourceDetection
  approved: boolean
  onApprove: (value: MappingApproval) => void
  onInvalidate: () => void
}) {
  const [mapping, setMapping] = useState(detection.mapping || {})
  const [name, setName] = useState('Generic agent trace')
  const providers = useProviders()
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState('')
  const assistant = useAction<{
    mapping: Record<string, string>
    assistance: unknown
  }>('sources.assist')
  return (
    <div className="mapping-review">
      <h4>
        {detection.knownProfile
          ? 'Known schema detected'
          : 'Review generic trace mapping'}
        {approved && (
          <span>
            <Check size={12} />
            Approved
          </span>
        )}
      </h4>
      <p className="muted small">
        The event-list path starts at the document root. Event fields use paths
        relative to an event; trajectory ID is relative to the root.
      </p>
      <Field label="Mapping profile name">
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <div className="mapping-fields">
        {Object.entries(mapping).map(([key, value]) => (
          <label key={key}>
            <span>{key.replace(/([A-Z])/g, ' $1')}</span>
            <input
              className="mono"
              value={value}
              placeholder="Not mapped"
              onChange={(e) => {
                onInvalidate()
                setMapping((m) => ({ ...m, [key]: e.target.value }))
              }}
            />
          </label>
        ))}
      </div>
      <details className="raw-details">
        <summary>Sample and schema preview</summary>
        <pre>
          {JSON.stringify(
            { schema: detection.schema, sample: detection.sample },
            null,
            2,
          )}
        </pre>
      </details>
      <details className="mapping-assistance">
        <summary>Optional model assistance</summary>
        <p className="muted small">
          Only the bounded schema and sample shown above are sent. Nothing is
          sent until you click the button; review the returned mapping before
          importing.
        </p>
        <div className="form-grid">
          <Field label="Provider">
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value)
                setModel(
                  providers.data?.find((p) => p.id === e.target.value)
                    ?.defaultModel || '',
                )
              }}
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
              placeholder="provider/model"
            />
          </Field>
        </div>
        <Button
          variant="secondary"
          disabled={!model || assistant.isPending}
          onClick={() =>
            assistant.mutate(
              { ref: detection.ref, provider, model, explicitConsent: true },
              {
                onSuccess: (value) => {
                  onInvalidate()
                  setMapping(value.mapping)
                },
              },
            )
          }
        >
          <Sparkles size={13} />
          {assistant.isPending
            ? 'Asking model…'
            : 'Send shown preview & suggest mapping'}
        </Button>
      </details>
      <Button
        variant="secondary"
        onClick={() =>
          onApprove({
            fingerprint: detection.fingerprint!,
            mapping,
            name,
            assistance: assistant.data?.assistance,
          })
        }
      >
        <Check size={13} />
        Approve mapping
      </Button>
    </div>
  )
}
