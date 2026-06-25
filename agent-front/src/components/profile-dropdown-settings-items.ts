import {
  BookOpenText,
  Building2,
  CircleUserRound,
  Database,
  Menu,
  ShieldCheck,
  Users,
  type LucideIcon,
} from 'lucide-react'

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

export const profileDropdownSystemItems: ReadonlyArray<{
  label: string
  section: 'system'
  page: string
  icon: LucideIcon
}> = [
  {
    label: '用户管理',
    section: 'system',
    page: 'user',
    icon: Users,
  },
  {
    label: '角色管理',
    section: 'system',
    page: 'role',
    icon: ShieldCheck,
  },
  {
    label: '菜单管理',
    section: 'system',
    page: 'menu',
    icon: Menu,
  },
  {
    label: '部门管理',
    section: 'system',
    page: 'dept',
    icon: Building2,
  },
  {
    label: '字典管理',
    section: 'system',
    page: 'dict',
    icon: BookOpenText,
  },
  {
    label: '文件管理',
    section: 'system',
    page: 'file',
    icon: Database,
  },
] as const
