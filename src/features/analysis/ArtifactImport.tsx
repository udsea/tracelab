import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { rpc } from '@/lib/api'
import { useUI, notify } from '@/stores/ui'
export function ArtifactImport() {
  const ui = useUI(),
    client = useQueryClient(),
    [uri, setUri] = useState(''),
    [name, setName] = useState('Probe score'),
    [measurement, setMeasurement] = useState('probe'),
    [eventColumn, setEventColumn] = useState('event_index'),
    [scoreColumn, setScoreColumn] = useState('score')
  const run = useMutation({
    mutationFn: () =>
      rpc<{ count: number }>('analysis.importParquet', {
        trajectoryId: ui.trajectoryId,
        uri,
        name,
        measurement,
        eventColumn,
        scoreColumn,
      }),
    onSuccess: (r) => {
      notify(`Imported ${r.count} scalar measurements`)
      void client.invalidateQueries({ queryKey: ['signals'] })
      void client.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (e: Error) => notify(e.message),
  })
  return (
    <details>
      <summary>Associate external scalar measurements</summary>
      <p>
        Parquet values reference existing event indices. Large tensors remain
        outside DuckDB; the file checksum and column mapping are retained.
      </p>
      <label className="field">
        Local Parquet file
        <input
          value={uri}
          onChange={(e) => setUri(e.target.value)}
          placeholder="/path/to/probe_scores.parquet"
        />
      </label>
      <label className="field">
        Signal name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        Measurement
        <select
          value={measurement}
          onChange={(e) => setMeasurement(e.target.value)}
        >
          {['probe', 'logit', 'sae'].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </label>
      <label className="field">
        Event index column
        <input
          value={eventColumn}
          onChange={(e) => setEventColumn(e.target.value)}
        />
      </label>
      <label className="field">
        Scalar value column
        <input
          value={scoreColumn}
          onChange={(e) => setScoreColumn(e.target.value)}
        />
      </label>
      <button
        disabled={!uri || run.isPending || !ui.trajectoryId}
        onClick={() => run.mutate()}
      >
        Import measurements
      </button>
    </details>
  )
}
