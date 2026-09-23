import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { rpc } from '@/lib/api'
import { notify, useUI } from '@/stores/ui'
import type {
  ClassifierDefinition,
  Experiment,
  Job,
  Page,
  Provider,
  TimelineData,
  Trajectory,
  Workspace,
} from '@/types/domain'
export const useWorkspaces = () =>
  useQuery({
    queryKey: ['workspaces'],
    queryFn: () => rpc<Workspace[]>('workspaces.list'),
  })
export const useExperiments = (workspaceId: string | null) =>
  useQuery({
    queryKey: ['experiments', workspaceId],
    queryFn: () => rpc<Experiment[]>('experiments.list', { workspaceId }),
    enabled: !!workspaceId,
  })
export const useTrajectories = (workspaceId: string | null) =>
  useQuery({
    queryKey: ['trajectories', workspaceId],
    queryFn: () =>
      rpc<Page<Trajectory>>('trajectories.list', { workspaceId, limit: 100 }),
    enabled: !!workspaceId,
  })
export const useTrajectory = (id: string | null) =>
  useQuery({
    queryKey: ['trajectory', id],
    queryFn: () =>
      rpc<{
        trajectory: Trajectory
        capabilities: {
          contextOnly: boolean
          checkpointRestored: boolean
          reason: string
        }
      }>('trajectories.get', { id }),
    enabled: !!id,
  })
export const useTimeline = (id: string | null) =>
  useQuery({
    queryKey: ['timeline', id],
    queryFn: () => rpc<TimelineData>('timeline', { trajectoryId: id }),
    enabled: !!id,
  })
export function useClassifiers() {
  const workspaceId = useUI((s) => s.workspaceId)
  return useQuery({
    queryKey: ['classifiers', workspaceId],
    queryFn: () =>
      rpc<ClassifierDefinition[]>('classifiers.list', { workspaceId }),
  })
}
export const useProviders = () =>
  useQuery({
    queryKey: ['providers'],
    queryFn: () => rpc<Provider[]>('providers.list'),
  })
export const useJobs = () =>
  useQuery({
    queryKey: ['jobs'],
    queryFn: () => rpc<Job[]>('jobs.list'),
    refetchInterval: 1500,
  })
export function useAction<T = unknown>(
  method: string,
  invalidate: string[] = [],
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (params: object) => rpc<T>(method, params),
    onSuccess: () => {
      invalidate.forEach((key) => {
        void client.invalidateQueries({ queryKey: [key] })
      })
    },
    onError: (error) => notify(error.message),
  })
}
