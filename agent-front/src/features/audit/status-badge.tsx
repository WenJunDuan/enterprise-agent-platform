import { Badge } from '@/components/ui/badge'
import type { TaskStatus, Verdict } from './types'
import { taskStatusLabels, verdictLabel } from './format'

type Tone = 'default' | 'secondary' | 'destructive' | 'outline'

const taskVariant: Record<TaskStatus, Tone> = {
  accepted: 'secondary',
  running: 'default',
  completed: 'outline',
  failed: 'destructive',
}

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  return (
    <Badge variant={taskVariant[status]} className='whitespace-nowrap'>
      {taskStatusLabels[status]}
    </Badge>
  )
}

export function VerdictBadge({ verdict }: { verdict?: Verdict }) {
  const variant: Tone =
    verdict === 'rejected' ? 'destructive' : verdict === 'approved' ? 'outline' : 'secondary'
  return (
    <Badge variant={variant} className='whitespace-nowrap'>
      {verdictLabel(verdict)}
    </Badge>
  )
}
