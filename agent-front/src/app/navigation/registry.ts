import { hasAccess } from '@/app/auth/access'
import type { AuthUser } from '@/types/auth'
import { FileText, LayoutDashboard } from 'lucide-react'
import type { NavGroup, NavItem, NavLink } from '@/components/layout/types'
import { normalizeBackendIconName } from './icon-registry'
import {
  getBackendPageByComponent,
  getBackendPageByPath,
} from './page-registry'
import type { BackendMenuRouter, BreadcrumbConfig } from './types'

const DEFAULT_AVATAR = '/avatars/01.png'

const MENU_GROUP_ORDER = ['总览', '业务'] as const

const STATIC_BREADCRUMBS: Record<string, BreadcrumbConfig[]> = {
  '/': [{ label: '仪表盘' }],
  '/audit': [{ label: '审核工作台' }],
  '/audit/submit': [
    { label: '审核工作台', href: '/audit' },
    { label: '报销提交' },
  ],
  '/ocr': [{ label: '文档识别' }],
  '/settings': [{ label: '系统管理' }, { label: '个人资料' }],
}

const LOCAL_BUSINESS_ITEMS: NavItem[] = [
  {
    title: '审核工作台',
    url: '/audit',
    icon: FileText,
  },
  {
    title: '文档识别',
    url: '/ocr',
    icon: FileText,
  },
]

type BackendMenuMatch = {
  breadcrumbs: BreadcrumbConfig[]
  fullPath: string
  router: BackendMenuRouter
}

function normalizePath(pathname: string) {
  return pathname.replace(/\/+$/, '') || '/'
}

function joinBackendPath(parentPath: string, currentPath: string) {
  const normalizedParentPath = normalizePath(parentPath)
  const normalizedCurrentPath = currentPath
    .replace(/^\/+/, '')
    .replace(/\/+$/, '')

  if (!normalizedCurrentPath || normalizedCurrentPath === '.') {
    return normalizedParentPath
  }

  if (currentPath.startsWith('/')) {
    return normalizePath(currentPath)
  }

  if (normalizedParentPath === '/') {
    return normalizePath(`/${normalizedCurrentPath}`)
  }

  return normalizePath(`${normalizedParentPath}/${normalizedCurrentPath}`)
}

function getMenuTitle(router: BackendMenuRouter) {
  return router.meta?.title || router.name || router.path
}

function resolveIcon(iconName?: string | null) {
  return normalizeBackendIconName(iconName)
}

function matchesBackendAccess(
  user: Pick<AuthUser, 'roles' | 'permissions'> | null | undefined,
  router: BackendMenuRouter
) {
  return hasAccess(user, {
    permissions: router.meta?.permission ? [router.meta.permission] : [],
    roles: router.meta?.roles ?? [],
  })
}

function buildBackendNavItems(
  routers: BackendMenuRouter[],
  user: Pick<AuthUser, 'roles' | 'permissions'> | null | undefined,
  parentPath = '/'
): NavLink[] {
  return routers.flatMap((router): NavLink[] => {
    if (router.hidden) {
      return []
    }

    const fullPath = joinBackendPath(parentPath, router.path)
    if (router.children?.length) {
      return buildBackendNavItems(router.children, user, fullPath)
    }

    const pageDefinition = getBackendPageByComponent(router.component)
    if (!pageDefinition || pageDefinition.fullPath !== fullPath) {
      return []
    }

    if (!matchesBackendAccess(user, router)) {
      return []
    }

    return [
      {
        title: getMenuTitle(router),
        url: fullPath,
        icon: resolveIcon(router.meta?.icon),
      },
    ]
  })
}

function findBackendMenuMatch(
  routers: BackendMenuRouter[],
  targetPath: string,
  parentPath = '/',
  breadcrumbs: BreadcrumbConfig[] = []
): BackendMenuMatch | null {
  for (const router of routers) {
    const fullPath = joinBackendPath(parentPath, router.path)
    const nextBreadcrumbs = [
      ...breadcrumbs,
      {
        label: getMenuTitle(router),
        href: getBackendPageByPath(fullPath) ? fullPath : undefined,
      },
    ]

    if (fullPath === targetPath) {
      return {
        breadcrumbs: nextBreadcrumbs,
        fullPath,
        router,
      }
    }

    if (router.children?.length) {
      const childMatch = findBackendMenuMatch(
        router.children,
        targetPath,
        fullPath,
        nextBreadcrumbs
      )
      if (childMatch) {
        return childMatch
      }
    }
  }

  return null
}

export function buildNavigationUser(user: AuthUser | null | undefined) {
  return {
    name: user?.nickname || user?.username || '当前用户',
    email: user?.email || '未设置邮箱',
    avatar: user?.avatar || DEFAULT_AVATAR,
  }
}

export function buildNavigationGroups(
  user: Pick<AuthUser, 'roles' | 'permissions'> | null | undefined,
  routers?: BackendMenuRouter[]
) {
  const groups = new Map<(typeof MENU_GROUP_ORDER)[number], NavItem[]>()

  groups.set('总览', [
    {
      title: '仪表盘',
      url: '/',
      icon: LayoutDashboard,
    },
  ])

  const backendItems: NavItem[] =
    routers?.flatMap((router): NavItem[] => {
      if (router.hidden) {
        return []
      }

      const fullPath = joinBackendPath('/', router.path)
      const childItems = router.children?.length
        ? buildBackendNavItems(router.children, user, fullPath)
        : []

      if (childItems.length > 0) {
        return [
          {
            title: getMenuTitle(router),
            icon: resolveIcon(router.meta?.icon),
            items: childItems,
          },
        ]
      }

      const pageDefinition = getBackendPageByComponent(router.component)
      if (!pageDefinition || pageDefinition.fullPath !== fullPath) {
        return []
      }

      if (!matchesBackendAccess(user, router)) {
        return []
      }

      return [
        {
          title: getMenuTitle(router),
          url: fullPath,
          icon: resolveIcon(router.meta?.icon),
        },
      ]
    }) ?? []

  const businessItems = [...LOCAL_BUSINESS_ITEMS, ...backendItems]
  if (businessItems.length > 0) {
    groups.set('业务', businessItems)
  }

  return MENU_GROUP_ORDER.map<NavGroup>((groupTitle) => ({
    title: groupTitle,
    items: groups.get(groupTitle) ?? [],
  })).filter((group) => group.items.length > 0)
}

export function getBreadcrumbsForPath(
  pathname: string,
  routers?: BackendMenuRouter[]
): BreadcrumbConfig[] {
  const normalizedPath = normalizePath(pathname)
  if (normalizedPath.startsWith('/audit/tasks/')) {
    return [{ label: '审核工作台', href: '/audit' }, { label: '任务详情' }]
  }

  const staticBreadcrumbs = STATIC_BREADCRUMBS[normalizedPath]
  if (staticBreadcrumbs) {
    return staticBreadcrumbs
  }

  const backendMatch = routers
    ? findBackendMenuMatch(routers, normalizedPath)
    : null
  if (backendMatch) {
    return backendMatch.breadcrumbs
  }

  return [{ label: '仪表盘' }]
}

export function findBackendRouteByPath(
  routers: BackendMenuRouter[],
  pathname: string
) {
  return findBackendMenuMatch(routers, normalizePath(pathname))
}
