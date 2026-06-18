import type { ApiResult } from '@/types/api'
import { toId, toIdList } from '@/lib/ids'
import { apiClient } from '@/lib/http'
import type { CheckableTreeNode } from './components/roles-checkable-tree'
import {
  buildRoleCreatePayload,
  buildRoleListQuery,
  buildRoleUpdatePayload,
  type PagedResult,
  type Role,
  type RoleCreateFormInput,
  type RoleDataScope,
  type RoleDataScopeUpdateInput,
  type RoleDetail,
  type RoleManagementSearch,
  type RoleStatusUpdateInput,
  type RoleUpdateFormInput,
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

function normalizeStatus(value: unknown): 0 | 1 {
  return Number(value ?? 1) === 0 ? 0 : 1
}

function normalizeDataScope(value: unknown): RoleDataScope {
  const parsed = Number(value ?? 1)
  if (parsed === 2 || parsed === 3 || parsed === 4 || parsed === 5) {
    return parsed
  }
  return 1
}

function normalizeRole(input: unknown): Role {
  const record = getRecord(input)
  return {
    id: toId(record.id),
    roleName: String(record.roleName ?? ''),
    roleKey: String(record.roleKey ?? ''),
    orderNum: Number(record.orderNum ?? 0),
    dataScope: normalizeDataScope(record.dataScope),
    status: normalizeStatus(record.status),
    remark: typeof record.remark === 'string' ? record.remark : null,
    createTime:
      typeof record.createTime === 'string' ? record.createTime : null,
  }
}

export async function fetchRoles(search: Partial<RoleManagementSearch>) {
  const response = await apiClient.get<ApiResult<PagedResult<unknown>>>(
    '/system/role/list',
    {
      params: buildRoleListQuery(search),
    }
  )

  const page = unwrapResult(response.data)
  return {
    pageNum: Number(page.pageNum ?? 1),
    pageSize: Number(page.pageSize ?? 10),
    total: Number(page.total ?? 0),
    pages: Number(page.pages ?? 0),
    records: (page.records ?? []).map(normalizeRole),
  } satisfies PagedResult<Role>
}

export async function fetchRoleDetail(roleId: string) {
  const response = await apiClient.get<ApiResult<unknown>>(
    `/system/role/${roleId}`
  )
  return normalizeRole(unwrapResult(response.data)) as RoleDetail
}

export async function fetchRoleMenuIds(roleId: string) {
  const response = await apiClient.get<ApiResult<Array<number | string>>>(
    `/system/role/${roleId}/menus`
  )
  return toIdList(unwrapResult(response.data))
}

export async function fetchRoleDeptIds(roleId: string) {
  const response = await apiClient.get<ApiResult<Array<number | string>>>(
    `/system/role/${roleId}/depts`
  )
  return toIdList(unwrapResult(response.data))
}

export async function createRole(input: RoleCreateFormInput) {
  const response = await apiClient.post<ApiResult<number | string>>(
    '/system/role',
    buildRoleCreatePayload(input)
  )
  return toId(unwrapResult(response.data))
}

export async function updateRole(input: RoleUpdateFormInput) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/role',
    buildRoleUpdatePayload(input)
  )
  return unwrapResult(response.data)
}

export async function deleteRoles(roleIds: string[]) {
  const response = await apiClient.delete<ApiResult<null>>(
    `/system/role/${roleIds.join(',')}`
  )
  return unwrapResult(response.data)
}

export async function changeRoleStatus(input: RoleStatusUpdateInput) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/role/changeStatus',
    null,
    {
      params: {
        roleId: toId(input.roleId),
        status: input.status,
      },
    }
  )
  return unwrapResult(response.data)
}

function normalizeTreeNode(input: unknown, seen: Set<string>): CheckableTreeNode[] {
  const record = getRecord(input)
  const id = toId(record.id ?? record.deptId ?? record.menuId)
  if (!id || id === '0' || seen.has(id)) {
    const children = Array.isArray(record.children) ? record.children : []
    return children.flatMap((child) => normalizeTreeNode(child, seen))
  }

  seen.add(id)
  const label = String(
    record.label ?? record.name ?? record.deptName ?? record.menuName ?? ''
  )
  const children = Array.isArray(record.children) ? record.children : []

  return [
    {
      id,
      label,
      children: children.flatMap((child) => normalizeTreeNode(child, seen)),
    },
  ]
}

export async function fetchMenuTreeSelect() {
  const response = await apiClient.get<ApiResult<unknown[]>>(
    '/system/menu/treeselect'
  )
  const seen = new Set<string>()
  return unwrapResult(response.data).flatMap((node) =>
    normalizeTreeNode(node, seen)
  )
}

export async function fetchDeptTreeSelect() {
  const response = await apiClient.get<ApiResult<unknown[]>>(
    '/system/dept/treeselect'
  )
  const seen = new Set<string>()
  return unwrapResult(response.data).flatMap((node) =>
    normalizeTreeNode(node, seen)
  )
}

export async function updateRoleDataScope(input: RoleDataScopeUpdateInput) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/role/dataScope',
    null,
    {
      params: {
        roleId: toId(input.roleId),
        dataScope: input.dataScope,
        deptIds:
          input.dataScope === 4 && input.deptIds.length > 0
            ? toIdList(input.deptIds).join(',')
            : undefined,
      },
    }
  )
  return unwrapResult(response.data)
}
