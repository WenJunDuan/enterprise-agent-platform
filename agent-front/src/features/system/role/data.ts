import { type RoleStatus } from './model'

export const roleStatusTone = new Map<RoleStatus, string>([
  [1, 'bg-teal-100/30 text-teal-900 dark:text-teal-200 border-teal-200'],
  [0, 'bg-neutral-300/40 border-neutral-300'],
])

export const roleStatuses = [
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
] as const

export function getRoleStatusLabel(status: RoleStatus | number | undefined) {
  return status === 1 ? '启用' : status === 0 ? '停用' : '未知'
}
