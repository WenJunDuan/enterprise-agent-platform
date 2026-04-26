import type { TaskStatus } from '../types'

interface Props {
  status: TaskStatus | string
}

const CONFIG: Record<string, { label: string; classes: string }> = {
  accepted: {
    label: '已接收',
    classes: 'bg-blue-100 text-blue-700',
  },
  running: {
    label: '审核中',
    classes: 'bg-yellow-100 text-yellow-700 animate-pulse',
  },
  completed: {
    label: '已完成',
    classes: 'bg-green-100 text-green-700',
  },
  failed: {
    label: '失败',
    classes: 'bg-red-100 text-red-700',
  },
}

export default function StatusBadge({ status }: Props) {
  const cfg = CONFIG[status] ?? { label: status, classes: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cfg.classes}`}>
      {cfg.label}
    </span>
  )
}
