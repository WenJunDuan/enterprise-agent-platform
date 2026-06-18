import { type LinkProps } from '@tanstack/react-router'
import { type LucideIcon } from 'lucide-react'

export type BackendMenuRouter = {
  name?: string
  path: string
  hidden?: boolean
  redirect?: string
  component?: string
  query?: string
  alwaysShow?: boolean
  meta?: {
    title?: string
    icon?: string
    noCache?: boolean
    requiresAuth?: boolean
    permission?: string
    roles?: string[]
    link?: string
  } | null
  children?: BackendMenuRouter[]
}

export type BreadcrumbConfig = {
  label: string
  href?: string
}

export type MenuGroupKey = '总览' | '系统'

export type MenuParentKey = 'system-management'

export type AppRouteDefinition = {
  key: string
  to: LinkProps['to'] | (string & {})
  title: string
  icon?: LucideIcon
  menu?: {
    group: MenuGroupKey
    order: number
    parent?: MenuParentKey
  }
  backendComponent?: string
  requiredPermissions?: string[]
  requiredRoles?: string[]
  breadcrumbs: BreadcrumbConfig[]
}

export type AppMenuParentDefinition = {
  key: MenuParentKey
  title: string
  icon?: LucideIcon
  group: MenuGroupKey
  order: number
}
