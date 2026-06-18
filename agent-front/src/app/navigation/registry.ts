import type { AuthUser } from '@/types/auth'
import { ClipboardList, ScanText, ScrollText } from 'lucide-react'
import type { NavGroup, NavItem } from '@/components/layout/types'
import { getBackendPageByPath } from './page-registry'
import type { BackendMenuRouter, BreadcrumbConfig } from './types'

const DEFAULT_AVATAR = '/avatars/01.png'

const MENU_GROUP_ORDER = ['发票审核', 'OCR 识别', '合同审查'] as const

const STATIC_BREADCRUMBS: Record<string, BreadcrumbConfig[]> = {
  '/': [{ label: '发票审核' }, { label: '发票审核清单' }],
  '/audit': [{ label: '发票审核' }, { label: '发票审核清单' }],
  '/audit/submit': [
    { label: '发票审核' },
    { label: '发票审核清单', href: '/audit' },
    { label: '新建审核' },
  ],
  '/ocr': [{ label: 'OCR 识别' }, { label: 'OCR 识别' }],
  '/contracts': [{ label: '合同审查' }, { label: '合同审查清单' }],
  '/settings': [{ label: '系统管理' }, { label: '个人资料' }],
}

const DOMAIN_NAV_GROUPS: Record<(typeof MENU_GROUP_ORDER)[number], NavItem[]> = {
  发票审核: [
    {
      title: '发票审核清单',
      url: '/audit',
      icon: ClipboardList,
    },
  ],
  'OCR 识别': [
    {
      title: 'OCR 识别',
      url: '/ocr',
      icon: ScanText,
    },
  ],
  合同审查: [
    {
      title: '合同审查清单',
      url: '/contracts',
      icon: ScrollText,
    },
  ],
}

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
  _user: Pick<AuthUser, 'roles' | 'permissions'> | null | undefined,
  _routers?: BackendMenuRouter[]
) {
  return MENU_GROUP_ORDER.map<NavGroup>((groupTitle) => ({
    title: groupTitle,
    items: DOMAIN_NAV_GROUPS[groupTitle],
  })).filter((group) => group.items.length > 0)
}

export function getBreadcrumbsForPath(
  pathname: string,
  routers?: BackendMenuRouter[]
): BreadcrumbConfig[] {
  const normalizedPath = normalizePath(pathname)
  if (normalizedPath.startsWith('/audit/tasks/')) {
    return [
      { label: '发票审核' },
      { label: '发票审核清单', href: '/audit' },
      { label: '任务详情' },
    ]
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

  return [{ label: '发票审核' }]
}

export function findBackendRouteByPath(
  routers: BackendMenuRouter[],
  pathname: string
) {
  return findBackendMenuMatch(routers, normalizePath(pathname))
}
