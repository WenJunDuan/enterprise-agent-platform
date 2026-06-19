import { Badge } from '@/components/ui/badge'

const statusLabels: Record<string, string> = {
  doing: '分析中',
  review: '待复核',
  done: '已完成',
  archived: '已归档',
}

export function StatusBadge({ status }: { status: string }) {
  const variant =
    status === 'review'
      ? 'secondary'
      : status === 'done'
        ? 'default'
        : 'outline'

  return <Badge variant={variant}>{statusLabels[status] ?? status}</Badge>
}
