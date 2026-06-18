import { CircleUserRound, type LucideIcon } from 'lucide-react'

export const profileDropdownSettingsItems: ReadonlyArray<{
  label: string
  to: '/settings'
  icon: LucideIcon
}> = [
  {
    label: '个人资料',
    to: '/settings',
    icon: CircleUserRound,
  },
] as const
