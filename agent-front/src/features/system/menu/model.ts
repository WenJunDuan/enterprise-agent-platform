import { toId } from '@/lib/ids'

export type MenuType = 'M' | 'C' | 'F'
export type MenuStatus = 0 | 1
export type BoolFlag = 0 | 1

export type MenuTreeNode = {
  menuId: string
  parentId: string
  menuName: string
  orderNum: number
  path: string | null
  component: string | null
  queryParam: string | null
  isFrame: BoolFlag
  isCache: BoolFlag
  menuType: MenuType
  visible: BoolFlag
  perms: string | null
  icon: string | null
  status: MenuStatus
  remark: string | null
  createTime: string | null
  children: MenuTreeNode[]
}

export type MenuDetail = MenuTreeNode

export type MenuListQuery = {
  menuName?: string
  status?: MenuStatus
}

export type MenuFormInput = {
  parentId: string
  menuName: string
  orderNum: string
  path: string
  component: string
  queryParam: string
  isFrame: '0' | '1'
  isCache: '0' | '1'
  menuType: MenuType
  visible: '0' | '1'
  perms: string
  icon: string
  status: '0' | '1'
  remark: string
}

export type MenuTypeFilter = 'all' | MenuType

export type MenuTreeViewItem = {
  id: string
  name: string
  type: 'folder' | 'file'
  children?: MenuTreeViewItem[]
}

function trimOrEmpty(value?: string | null) {
  return value?.trim() ?? ''
}

function toNullableText(value?: string | null) {
  const normalized = trimOrEmpty(value)
  return normalized === '' ? null : normalized
}

function toRequiredText(value?: string | null) {
  const normalized = trimOrEmpty(value)
  return normalized === '' ? '0' : normalized
}

export function buildMenuCreatePayload(input: MenuFormInput) {
  return {
    parentId: toRequiredText(input.parentId),
    menuName: trimOrEmpty(input.menuName),
    orderNum: Number(trimOrEmpty(input.orderNum) || '0'),
    path: toNullableText(input.path),
    component: toNullableText(input.component),
    queryParam: toNullableText(input.queryParam),
    isFrame: Number(input.isFrame) === 0 ? 0 : 1,
    isCache: Number(input.isCache) === 0 ? 0 : 1,
    menuType: input.menuType,
    visible: Number(input.visible) === 0 ? 0 : 1,
    perms: toNullableText(input.perms),
    icon: toNullableText(input.icon),
    status: Number(input.status) === 0 ? 0 : 1,
    remark: toNullableText(input.remark),
  }
}

export function buildMenuUpdatePayload(input: MenuFormInput, menuId: string) {
  return {
    menuId: toId(menuId),
    ...buildMenuCreatePayload(input),
  }
}

export function buildMenuFormDefaults(
  detail?: Partial<MenuDetail>,
  parentId?: string
): MenuFormInput {
  return {
    parentId: parentId ?? detail?.parentId ?? '0',
    menuName: detail?.menuName ?? '',
    orderNum: String(detail?.orderNum ?? 0),
    path: detail?.path ?? '',
    component: detail?.component ?? '',
    queryParam: detail?.queryParam ?? '',
    isFrame: String(detail?.isFrame ?? 1) as '0' | '1',
    isCache: String(detail?.isCache ?? 0) as '0' | '1',
    menuType: detail?.menuType ?? 'M',
    visible: String(detail?.visible ?? 1) as '0' | '1',
    perms: detail?.perms ?? '',
    icon: detail?.icon ?? '',
    status: String(detail?.status ?? 1) as '0' | '1',
    remark: detail?.remark ?? '',
  }
}

export function findMenuById(
  nodes: MenuTreeNode[],
  menuId: string
): MenuTreeNode | undefined {
  for (const node of nodes) {
    if (node.menuId === menuId) {
      return node
    }

    const childMatch = findMenuById(node.children ?? [], menuId)
    if (childMatch) {
      return childMatch
    }
  }

  return undefined
}

export function findFirstMenuId(nodes: MenuTreeNode[]) {
  return nodes[0]?.menuId ?? null
}

export function filterMenuTree(
  nodes: MenuTreeNode[],
  keyword: string,
  typeFilter: MenuTypeFilter = 'all'
): MenuTreeNode[] {
  const normalizedKeyword = trimOrEmpty(keyword).toLowerCase()

  if (!normalizedKeyword && typeFilter === 'all') {
    return nodes
  }

  return nodes.flatMap((node) => {
    const children = filterMenuTree(node.children ?? [], normalizedKeyword, typeFilter)
    const isKeywordMatch =
      !normalizedKeyword ||
      node.menuName.toLowerCase().includes(normalizedKeyword)
    const isTypeMatch = typeFilter === 'all' || node.menuType === typeFilter

    if (!isKeywordMatch || !isTypeMatch) {
      if (children.length === 0) {
        return []
      }

      return [{ ...node, children }]
    }

    return [{ ...node, children }]
  })
}

export function collectMenuBranchIds(
  nodes: MenuTreeNode[],
  menuId: string
): Set<string> {
  const target = findMenuById(nodes, menuId)

  if (!target) {
    return new Set()
  }

  const ids = new Set<string>()

  function visit(node: MenuTreeNode) {
    ids.add(node.menuId)
    ;(node.children ?? []).forEach(visit)
  }

  visit(target)
  return ids
}

export function dedupeMenuTreeRoots(nodes: MenuTreeNode[]) {
  const descendantIds = new Set<string>()

  function collectDescendants(children: MenuTreeNode[]) {
    for (const child of children) {
      descendantIds.add(child.menuId)
      collectDescendants(child.children ?? [])
    }
  }

  nodes.forEach((node) => collectDescendants(node.children ?? []))

  return nodes.filter((node) => !descendantIds.has(node.menuId))
}

export function buildMenuTreeViewItems(
  nodes: MenuTreeNode[]
): MenuTreeViewItem[] {
  return nodes.map((node) => {
    const children = buildMenuTreeViewItems(node.children ?? [])

    return {
      id: node.menuId,
      name: node.menuName,
      type: children.length > 0 ? 'folder' : 'file',
      children: children.length > 0 ? children : undefined,
    }
  })
}

export function getMenuRootLabel(nodes: MenuTreeNode[]) {
  return findMenuById(nodes, '0')?.menuName ?? '顶级菜单'
}

export function collectMenuAncestorIds(
  nodes: MenuTreeNode[],
  targetMenuId: string
): string[] {
  function visit(branch: MenuTreeNode[], ancestors: string[]): string[] | null {
    for (const node of branch) {
      if (node.menuId === targetMenuId) {
        return ancestors
      }

      const matched = visit(node.children ?? [], [...ancestors, node.menuId])
      if (matched) {
        return matched
      }
    }

    return null
  }

  return visit(nodes, []) ?? []
}

export function createDefaultExpandedMenuIds(nodes: MenuTreeNode[]) {
  return new Set(
    nodes
      .filter((node) => (node.children?.length ?? 0) > 0)
      .map((node) => node.menuId)
  )
}

export function ensureMenuPathExpanded(
  expandedIds: Set<string>,
  nodes: MenuTreeNode[],
  targetMenuId: string | null
) {
  if (!targetMenuId) {
    return new Set(expandedIds)
  }

  const next = new Set(expandedIds)
  collectMenuAncestorIds(nodes, targetMenuId).forEach((menuId) => next.add(menuId))
  return next
}

export function findNextMenuOrderNum(nodes: MenuTreeNode[], parentId: string) {
  let currentMax = -1

  function visit(branch: MenuTreeNode[]) {
    for (const node of branch) {
      if (node.parentId === parentId) {
        currentMax = Math.max(currentMax, node.orderNum)
      }

      visit(node.children ?? [])
    }
  }

  visit(nodes)
  return currentMax >= 0 ? currentMax + 1 : 0
}
