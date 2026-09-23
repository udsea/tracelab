import {
  AlertCircle,
  Check,
  Circle,
  GitBranch,
  LoaderCircle,
  X,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import type { TrajectoryStatus } from '@/types/domain'
export function Status({
  status,
  small = false,
}: {
  status: TrajectoryStatus | string
  small?: boolean
}) {
  const Icon =
    status === 'success' || status === 'complete'
      ? Check
      : status === 'running'
        ? LoaderCircle
        : status === 'error' || status === 'failed' || status === 'failure'
          ? X
          : Circle
  return (
    <span className={`status status-${status} ${small ? 'status-small' : ''}`}>
      <Icon
        size={small ? 11 : 12}
        className={status === 'running' ? 'spin' : ''}
      />
      {!small && (status === 'unknown' ? 'Unscored' : status)}
    </span>
  )
}
export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon || <GitBranch size={25} />}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  )
}
export function Loading({ text = 'Loading trajectory…' }: { text?: string }) {
  return (
    <div className="loading-state">
      <LoaderCircle size={18} className="spin" />
      {text}
    </div>
  )
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error
  retry?: () => void
}) {
  return (
    <div className="error-state">
      <AlertCircle size={20} />
      <strong>Something needs attention</strong>
      <p>{error.message}</p>
      {retry && (
        <Button variant="outline" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  )
}
export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  )
}
