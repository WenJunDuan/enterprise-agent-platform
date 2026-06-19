import type { AuthUser } from '@/types/auth'
import { ClipboardList, FileSearch, History, ScanText } from 'lucide-react'
import type { NavGroup, NavItem } from '@/components/layout/types'
import { getBackendPageByPath } from './page-registry'
import type { BackendMenuRouter, BreadcrumbConfig } from './types'

const DEFAULT_AVATAR = '/avatars/01.png'

const MENU_GROUP_ORDER = ['智能报销审核', '智能 OCR', '智能招投标审核'] as const

const STATIC_BREADCRUMBS: Record<string, BreadcrumbConfig[]> = {
  '/': [{ label: '智能报销审核' }, { label: '报销审核' }],
  '/audit': [{ label: '智能报销审核' }, { label: '报销审核' }],
  '/audit/submit': [
    { label: '智能报销审核' },
    { label: '报销审核', href: '/audit' },
    { label: '新建报销审核' },
  ],
  '/ocr': [{ label: '智能 OCR' }, { label: 'OCR 识别' }],
  '/contracts': [{ label: '智能招投标审核' }, { label: '项目管理' }],
  '/contracts/tender-review': [
    { label: '智能招投标审核' },
    { label: '项目管理' },
  ],
  '/contracts/tender-review/history': [
    { label: '智能招投标审核' },
    { label: '历史评审' },
  ],
  '/settings': [{ label: '系统管理' }, { label: '个人资料' }],
}

const DOMAIN_NAV_GROUPS: Record<(typeof MENU_GROUP_ORDER)[number], NavItem[]> =
  {
    智能报销审核: [
      {
        title: '报销审核',
        url: '/audit',
        icon: ClipboardList,
      },
    ],
    '智能 OCR': [
      {
        title: 'OCR 识别',
        url: '/ocr',
        icon: ScanText,
      },
    ],
    智能招投标审核: [
      {
        title: '项目管理',
        url: '/contracts/tender-review',
        icon: FileSearch,
      },
      {
        title: '历史评审',
        url: '/contracts/tender-review/history',
        icon: History,
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
      { label: '智能报销审核' },
      { label: '报销审核', href: '/audit' },
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

  return [{ label: '智能报销审核' }]
}

export function findBackendRouteByPath(
  routers: BackendMenuRouter[],
  pathname: string
) {
  return findBackendMenuMatch(routers, normalizePath(pathname))
}
