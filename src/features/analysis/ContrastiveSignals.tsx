import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { rpc } from '@/lib/api'
import { useUI, notify } from '@/stores/ui'
import { useSignals, useOverview } from './queries'
interface Delta {
  control: number
  treatment: number
  delta: number
}
interface Comparison {
  tools: Record<string, Delta>
  eventTypes: Record<string, Delta>
  signals: Record<string, Delta>
  ruleMatchCounts: Record<string, Delta>
  unmatchedSignals: string[]
  interpretation: string
}
export function ContrastiveSignals({
  left,
  right,
}: {
  left: string
  right: string
}) {
  const ui = useUI(),
    query = useQuery({
      queryKey: ['analysis-comparison', left, right],
      queryFn: () =>
        rpc<Comparison>('analysis.compare', {
          controlId: left,
          treatmentId: right,
        }),
      enabled: !!left && !!right && left !== right,
    })
  const client = useQueryClient()
  const saveComparison = useMutation({
    mutationFn: async () => {
      const definition = await rpc<{ id: string }>('analysis.save', {
        name: 'Matched-condition comparison',
        detectorType: 'contrastive',
        parameters: {
          controlId: left,
          treatmentId: right,
          matching: 'manual',
          interpretation:
            'Descriptive comparison, not a sandbagging or causal judgment',
        },
      })
      await rpc('analysis.run', {
        definitionId: definition.id,
        trajectoryIds: [left, right],
      })
      await client.invalidateQueries({ queryKey: ['jobs'] })
      notify(
        'Contrastive analysis started; divergence evidence will appear on the treatment trajectory',
      )
    },
    onError: (e: Error) => notify(e.message),
  })
  const a = useOverview(left),
    b = useOverview(right),
    sa = useSignals(left),
    sb = useSignals(right)
  return (
    <section className="contrastive-signals">
      <h3>Observed branch comparison</h3>
      <p>
        Capability suppression requires matched model/task conditions; these
        descriptive differences alone do not establish sandbagging.
      </p>
      {[
        { id: left, data: a.data, signals: sa.data, label: 'CONTROL' },
        { id: right, data: b.data, signals: sb.data, label: 'TREATMENT' },
      ].map((row) => (
        <div key={row.id}>
          <strong>{row.label}</strong>
          <div className="contrastive-track">
            {row.data?.outline
              .filter((n) => n.kind === 'segment' || n.kind === 'episode')
              .map((n) => (
                <button
                  key={n.id}
                  title={`${n.label} #${n.startEventIndex}–${n.endEventIndex}`}
                  style={{
                    left: `${(100 * n.startEventIndex) / Math.max(1, row.data!.coordinates.points.length)}%`,
                    width: `${Math.max(0.3, (100 * (n.endEventIndex - n.startEventIndex + 1)) / Math.max(1, row.data!.coordinates.points.length))}%`,
                  }}
                  onClick={() => {
                    ui.selectTrajectory(row.id)
                    ui.focus(n.startEventIndex, n.endEventIndex, n.label)
                  }}
                />
              ))}
          </div>
          <div className="contrastive-track signals">
            {row.signals?.map((s) => (
              <button
                key={s.id}
                title={`${s.name}: ${s.score ?? s.label}`}
                style={{
                  left: `${(100 * s.startEventIndex) / Math.max(1, row.data?.coordinates.points.length ?? 1)}%`,
                  width: `${Math.max(0.3, (100 * (s.endEventIndex - s.startEventIndex + 1)) / Math.max(1, row.data?.coordinates.points.length ?? 1))}%`,
                }}
                onClick={() => {
                  ui.selectTrajectory(row.id)
                  ui.set({ signalId: s.id })
                }}
              />
            ))}
          </div>
        </div>
      ))}
      <button
        disabled={!query.data || saveComparison.isPending}
        onClick={() => saveComparison.mutate()}
      >
        Save contrastive analysis
      </button>
      {query.data && (
        <>
          <p className="muted">{query.data.interpretation}</p>
          {(['tools', 'eventTypes', 'signals', 'ruleMatchCounts'] as const).map(
            (field) => (
              <details key={field} open={field === 'signals'}>
                <summary>
                  {field === 'signals'
                    ? 'Mean emitted signal scores'
                    : field === 'ruleMatchCounts'
                      ? 'Rule match counts (zero only after completed execution)'
                      : field}{' '}
                  deltas
                </summary>
                <table>
                  <thead>
                    <tr>
                      <th>Measurement</th>
                      <th>Control</th>
                      <th>Treatment</th>
                      <th>Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(query.data![field]).map(([k, v]) => (
                      <tr key={k}>
                        <td>{k}</td>
                        <td>{v.control.toFixed(2)}</td>
                        <td>{v.treatment.toFixed(2)}</td>
                        <td>{v.delta.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            ),
          )}
          {!!query.data.unmatchedSignals.length && (
            <p>
              Unmatched detector lanes: {query.data.unmatchedSignals.join(', ')}
              . Run the same detector version on both trajectories to compare.
            </p>
          )}
        </>
      )}
      {query.error && <p>{query.error.message}</p>}
    </section>
  )
}
