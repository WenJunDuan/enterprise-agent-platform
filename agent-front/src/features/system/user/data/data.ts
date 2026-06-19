import { CircleHelp, Mars, Venus } from 'lucide-react'
import { type UserSex, type UserStatus } from './schema'

export const userStatusTone = new Map<UserStatus, string>([
  [1, 'bg-teal-100/30 text-teal-900 dark:text-teal-200 border-teal-200'],
  [0, 'bg-neutral-300/40 border-neutral-300'],
])

export const userStatuses = [
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
] as const

export const userSexOptions = [
  { label: '未知', value: '0', icon: CircleHelp },
  { label: '男', value: '1', icon: Mars },
  { label: '女', value: '2', icon: Venus },
] as const

export function getUserStatusLabel(status: UserStatus | number | undefined) {
  return status === 1 ? '启用' : status === 0 ? '停用' : '未知'
}

export function getUserSexLabel(sex: UserSex | number | undefined) {
  return sex === 1 ? '男' : sex === 2 ? '女' : '未知'
}
