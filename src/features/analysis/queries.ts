import { useQuery } from '@tanstack/react-query'
import { rpc } from '@/lib/api'
import type { AnalysisSignal, Overview } from '@/types/analysis'
export const useOverview = (id: string | null) =>
  useQuery({
    queryKey: ['overview', id],
    queryFn: () => rpc<Overview>('analysis.overview', { trajectoryId: id }),
    enabled: !!id,
    staleTime: 60000,
  })
export const useSignals = (id: string | null) =>
  useQuery({
    queryKey: ['signals', id],
    queryFn: () =>
      rpc<AnalysisSignal[]>('analysis.signals', { trajectoryId: id }),
    enabled: !!id,
  })
