import type { AuthUser } from '@/types/auth'
import { ClipboardList, FileSearch, History, ScanText } from 'lucide-react'
import type { NavGroup, NavItem } from '@/components/layout/types'
import {
  filterNavigationGroupsByVisibility,
  type NavigationMenuVisibility,
} from './menu-visibility'
import { getBackendPageByPath } from './page-registry'
import { getEnabledTenderScenarios } from './tender-scenarios'
import type { BackendMenuRouter, BreadcrumbConfig } from './types'
import type { TenderScenario } from '@/features/contract/tender-review/types'

const DEFAULT_AVATAR = '/avatars/01.png'

const MENU_GROUP_ORDER = ['智能招投标审核', '智能报销审核', '智能 OCR'] as const

const STATIC_BREADCRUMBS: Record<string, BreadcrumbConfig[]> = {
  '/': [{ label: '智能报销审核' }, { label: '报销审核' }],
  '/audit': [{ label: '智能报销审核' }, { label: '报销审核' }],
  '/audit/submit': [
    { label: '智能报销审核' },
    { label: '报销审核', href: '/audit' },
    { label: '新建报销审核' },
  ],
  '/ocr': [{ label: '智能 OCR' }, { label: 'OCR 识别' }],
  '/contracts': [{ label: '智能招投标审核' }, { label: '评审列表' }],
  '/contracts/tender/list': [
    { label: '智能招投标审核' },
    { label: '专家辅助' },
  ],
  '/contracts/tender/self-check': [
    { label: '智能招投标审核' },
    { label: '投标自查' },
  ],
  '/contracts/tender/post-eval': [
    { label: '智能招投标审核' },
    { label: '评后监督' },
  ],
  '/contracts/tender/detail': [
    { label: '智能招投标审核' },
    { label: '专家辅助', href: '/contracts/tender/list' },
    { label: '分析中心' },
  ],
  '/contracts/tender/history': [
    { label: '智能招投标审核' },
    { label: '历史评审' },
  ],
  '/settings': [{ label: '系统管理' }, { label: '个人资料' }],
}

function buildTenderScenarioItems(enabledScenarios: TenderScenario[]): NavItem[] {
  const items: NavItem[] = []
  if (enabledScenarios.includes('bidder_self_check')) {
    items.push({
      title: '投标自查',
      url: '/contracts/tender/self-check',
      icon: FileSearch,
    })
  }
  if (enabledScenarios.includes('expert_assist')) {
    items.push({
      title: '专家辅助',
      url: '/contracts/tender/list',
      icon: FileSearch,
    })
  }
  if (enabledScenarios.includes('post_eval_monitor')) {
    items.push({
      title: '评后监督',
      url: '/contracts/tender/post-eval',
      icon: FileSearch,
    })
  }
  return items
}

function getDomainNavGroups(
  enabledScenarios: TenderScenario[]
): Record<(typeof MENU_GROUP_ORDER)[number], NavItem[]> {
  return {
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
      ...buildTenderScenarioItems(enabledScenarios),
      {
        title: '历史评审',
        url: '/contracts/tender/history',
        icon: History,
      },
    ],
  }
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

export function getNavigationMenuDefinitions(
  enabledScenarios: TenderScenario[] = getEnabledTenderScenarios()
) {
  const domainNavGroups = getDomainNavGroups(enabledScenarios)
  return MENU_GROUP_ORDER.map<NavGroup>((groupTitle) => ({
    title: groupTitle,
    items: domainNavGroups[groupTitle],
  })).filter((group) => group.items.length > 0)
}

export function buildNavigationGroups(
  _user: Pick<AuthUser, 'roles' | 'permissions'> | null | undefined,
  _routers?: BackendMenuRouter[],
  visibility?: NavigationMenuVisibility,
  enabledScenarios: TenderScenario[] = getEnabledTenderScenarios()
) {
  return filterNavigationGroupsByVisibility(
    getNavigationMenuDefinitions(enabledScenarios),
    visibility
  )
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
