import type { ApiResult } from '@/types/api'
import { toId } from '@/lib/ids'
import { apiClient } from '@/lib/http'
import {
  buildMenuCreatePayload,
  buildMenuUpdatePayload,
  dedupeMenuTreeRoots,
  type BoolFlag,
  type MenuDetail,
  type MenuFormInput,
  type MenuListQuery,
  type MenuStatus,
  type MenuTreeNode,
  type MenuType,
} from './model'

function unwrapResult<T>(result: ApiResult<T>) {
  return result.data
}

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

export async function fetchMenuTree(search?: Partial<MenuListQuery>) {
  const response = await apiClient.get<ApiResult<unknown[]>>('/system/menu/list', {
    params: {
      menuName: search?.menuName?.trim() || undefined,
      status: search?.status,
    },
  })

  return dedupeMenuTreeRoots(unwrapResult(response.data).map(normalizeMenuNode))
}

export async function fetchMenuDetail(menuId: string) {
  const response = await apiClient.get<ApiResult<unknown>>(`/system/menu/${menuId}`)

  return normalizeMenuNode(unwrapResult(response.data)) as MenuDetail
}

export async function createMenu(input: MenuFormInput) {
  const response = await apiClient.post<ApiResult<string | number | null>>(
    '/system/menu',
    buildMenuCreatePayload(input)
  )

  const data = unwrapResult(response.data)
  return toId(data)
}

export async function updateMenu(input: MenuFormInput, menuId: string) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/menu',
    buildMenuUpdatePayload(input, menuId)
  )

  return unwrapResult(response.data)
}

export async function deleteMenu(menuId: string) {
  const response = await apiClient.delete<ApiResult<null>>(
    `/system/menu/${menuId}`
  )

  return unwrapResult(response.data)
}
