import { toId } from '@/lib/ids'
import {
  buildMenuCreatePayload,
  buildMenuUpdatePayload,
  dedupeMenuTreeRoots,
  filterMenuTree,
  type BoolFlag,
  type MenuDetail,
  type MenuFormInput,
  type MenuListQuery,
  type MenuStatus,
  type MenuTreeNode,
  type MenuType,
} from './model'

const STORAGE_KEY = 'enterprise-agent-front:system-menu-tree:v1'

const defaultMenuTree: MenuTreeNode[] = [
  {
    menuId: '100',
    parentId: '0',
    menuName: '系统管理',
    orderNum: 0,
    path: 'system',
    component: null,
    queryParam: null,
    isFrame: 1,
    isCache: 0,
    menuType: 'M',
    visible: 1,
    perms: null,
    icon: 'settings',
    status: 1,
    remark: '本地 JSON 系统菜单根节点',
    createTime: '2026-06-25 00:00:00',
    children: [
      {
        menuId: '101',
        parentId: '100',
        menuName: '用户管理',
        orderNum: 0,
        path: 'user',
        component: 'system/user/index',
        queryParam: null,
        isFrame: 1,
        isCache: 0,
        menuType: 'C',
        visible: 1,
        perms: null,
        icon: 'users',
        status: 1,
        remark: '本地 JSON 数据',
        createTime: '2026-06-25 00:00:00',
        children: [],
      },
      {
        menuId: '102',
        parentId: '100',
        menuName: '角色管理',
        orderNum: 1,
        path: 'role',
        component: 'system/role/index',
        queryParam: null,
        isFrame: 1,
        isCache: 0,
        menuType: 'C',
        visible: 1,
        perms: null,
        icon: 'shield-check',
        status: 1,
        remark: '本地 JSON 数据',
        createTime: '2026-06-25 00:00:00',
        children: [],
      },
      {
        menuId: '103',
        parentId: '100',
        menuName: '菜单管理',
        orderNum: 2,
        path: 'menu',
        component: 'system/menu/index',
        queryParam: null,
        isFrame: 1,
        isCache: 0,
        menuType: 'C',
        visible: 1,
        perms: null,
        icon: 'menu',
        status: 1,
        remark: '本地 JSON 数据',
        createTime: '2026-06-25 00:00:00',
        children: [],
      },
      {
        menuId: '104',
        parentId: '100',
        menuName: '部门管理',
        orderNum: 3,
        path: 'dept',
        component: 'system/dept/index',
        queryParam: null,
        isFrame: 1,
        isCache: 0,
        menuType: 'C',
        visible: 1,
        perms: null,
        icon: 'building-2',
        status: 1,
        remark: '本地 JSON 数据',
        createTime: '2026-06-25 00:00:00',
        children: [],
      },
      {
        menuId: '105',
        parentId: '100',
        menuName: '字典管理',
        orderNum: 4,
        path: 'dict',
        component: 'system/dict/index',
        queryParam: null,
        isFrame: 1,
        isCache: 0,
        menuType: 'C',
        visible: 1,
        perms: null,
        icon: 'book-open-text',
        status: 1,
        remark: '本地 JSON 数据',
        createTime: '2026-06-25 00:00:00',
        children: [],
      },
      {
        menuId: '106',
        parentId: '100',
        menuName: '文件管理',
        orderNum: 5,
        path: 'file',
        component: 'system/file/index',
        queryParam: null,
        isFrame: 1,
        isCache: 0,
        menuType: 'C',
        visible: 1,
        perms: null,
        icon: 'database',
        status: 1,
        remark: '本地 JSON 数据',
        createTime: '2026-06-25 00:00:00',
        children: [],
      },
    ],
  },
]

function getRecord(input: unknown) {
  return (input && typeof input === 'object' ? input : {}) as Record<
    string,
    unknown
  >
}

function normalizeMenuType(value: unknown): MenuType {
  if (value === 'C' || value === 'F') {
    return value
  }

  return 'M'
}

function normalizeBoolFlag(value: unknown, fallback: BoolFlag): BoolFlag {
  return Number(value) === 0 ? 0 : Number(value) === 1 ? 1 : fallback
}

function normalizeStatus(value: unknown): MenuStatus {
  return Number(value) === 0 ? 0 : 1
}

function normalizeNullableText(value: unknown) {
  if (typeof value !== 'string') {
    return null
  }

  const normalized = value.trim()
  return normalized === '' ? null : normalized
}

function normalizeMenuNode(input: unknown): MenuTreeNode {
  const record = getRecord(input)
  const children = Array.isArray(record.children)
    ? record.children.map(normalizeMenuNode)
    : []

  return {
    menuId: toId(record.menuId ?? record.id) || '0',
    parentId: toId(record.parentId) || '0',
    menuName: String(record.menuName ?? record.label ?? ''),
    orderNum: Number(record.orderNum ?? 0),
    path: normalizeNullableText(record.path),
    component: normalizeNullableText(record.component),
    queryParam: normalizeNullableText(record.queryParam),
    isFrame: normalizeBoolFlag(record.isFrame, 1),
    isCache: normalizeBoolFlag(record.isCache, 0),
    menuType: normalizeMenuType(record.menuType),
    visible: normalizeBoolFlag(record.visible, 1),
    perms: normalizeNullableText(record.perms),
    icon: normalizeNullableText(record.icon),
    status: normalizeStatus(record.status),
    remark: normalizeNullableText(record.remark),
    createTime:
      typeof record.createTime === 'string' ? record.createTime : null,
    children,
  }
}

function cloneMenuTree(nodes: MenuTreeNode[]) {
  return JSON.parse(JSON.stringify(nodes)) as MenuTreeNode[]
}

function getStorage() {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    return window.localStorage
  } catch {
    return null
  }
}

function readMenuTree() {
  const storage = getStorage()
  if (!storage) {
    return cloneMenuTree(defaultMenuTree)
  }

  try {
    const rawValue = storage.getItem(STORAGE_KEY)
    if (!rawValue) {
      return cloneMenuTree(defaultMenuTree)
    }

    const parsedValue = JSON.parse(rawValue)
    if (!Array.isArray(parsedValue)) {
      return cloneMenuTree(defaultMenuTree)
    }

    return dedupeMenuTreeRoots(parsedValue.map(normalizeMenuNode))
  } catch {
    return cloneMenuTree(defaultMenuTree)
  }
}

function writeMenuTree(nodes: MenuTreeNode[]) {
  const storage = getStorage()
  if (!storage) {
    return
  }

  storage.setItem(STORAGE_KEY, JSON.stringify(nodes))
}

function flattenMenuTree(nodes: MenuTreeNode[]) {
  const result: MenuTreeNode[] = []

  function visit(node: MenuTreeNode) {
    result.push(node)
    node.children.forEach(visit)
  }

  nodes.forEach(visit)
  return result
}

function createMenuId(nodes: MenuTreeNode[]) {
  const maxNumericId = flattenMenuTree(nodes).reduce((currentMax, node) => {
    const numericId = Number(node.menuId)
    return Number.isFinite(numericId) ? Math.max(currentMax, numericId) : currentMax
  }, 100)

  return String(maxNumericId + 1)
}

function mapMenuTree(
  nodes: MenuTreeNode[],
  mapper: (node: MenuTreeNode) => MenuTreeNode | null
): MenuTreeNode[] {
  return nodes.flatMap((node) => {
    const mappedNode = mapper({
      ...node,
      children: mapMenuTree(node.children, mapper),
    })

    return mappedNode ? [mappedNode] : []
  })
}

function appendMenuNode(nodes: MenuTreeNode[], parentId: string, node: MenuTreeNode) {
  if (parentId === '0') {
    return [...nodes, node]
  }

  let appended = false
  const nextNodes = mapMenuTree(nodes, (currentNode) => {
    if (currentNode.menuId !== parentId) {
      return currentNode
    }

    appended = true
    return {
      ...currentNode,
      children: [...currentNode.children, node],
    }
  })

  return appended ? nextNodes : [...nodes, node]
}

export async function fetchMenuTree(search?: Partial<MenuListQuery>) {
  const tree = readMenuTree()
  const keyword = search?.menuName?.trim() ?? ''
  const status = search?.status

  return filterMenuTree(tree, keyword).flatMap((node) => {
    if (status === undefined) {
      return [node]
    }

    const filterByStatus = (nodes: MenuTreeNode[]): MenuTreeNode[] =>
      nodes.flatMap((currentNode) => {
        const children = filterByStatus(currentNode.children)
        if (currentNode.status === status || children.length > 0) {
          return [{ ...currentNode, children }]
        }

        return []
      })

    return filterByStatus([node])
  })
}

export async function fetchMenuDetail(menuId: string) {
  const matchedMenu = flattenMenuTree(readMenuTree()).find(
    (node) => node.menuId === menuId
  )

  return (matchedMenu ?? normalizeMenuNode({ menuId: '0' })) as MenuDetail
}

export async function createMenu(input: MenuFormInput) {
  const currentTree = readMenuTree()
  const menuId = createMenuId(currentTree)
  const payload = buildMenuCreatePayload(input)
  const node = normalizeMenuNode({
    ...payload,
    menuId,
    createTime: new Date().toLocaleString('zh-CN', { hour12: false }),
    children: [],
  })

  writeMenuTree(appendMenuNode(currentTree, node.parentId, node))
  return toId(menuId)
}

export async function updateMenu(input: MenuFormInput, menuId: string) {
  const payload = buildMenuUpdatePayload(input, menuId)
  const currentTree = readMenuTree()
  const nextTree = mapMenuTree(currentTree, (node) =>
    node.menuId === menuId
      ? normalizeMenuNode({
          ...node,
          ...payload,
          children: node.children,
        })
      : node
  )

  writeMenuTree(nextTree)
  return null
}

export async function deleteMenu(menuId: string) {
  writeMenuTree(
    mapMenuTree(readMenuTree(), (node) => (node.menuId === menuId ? null : node))
  )
  return null
}
