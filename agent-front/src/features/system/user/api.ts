import type { ApiResult } from '@/types/api'
import { toId, toIdList } from '@/lib/ids'
import { apiClient } from '@/lib/http'
import type {
  DeptTreeNode,
  PagedResult,
  User,
  UserEditDetail,
  UserRoleOption,
} from './data/schema'
import {
  buildResetPasswordPayload,
  buildUserCreatePayload,
  buildUserListQuery,
  buildUserStatusPayload,
  buildUserUpdatePayload,
  type ResetPasswordFormInput,
  type UserCreateFormInput,
  type UserManagementSearch,
  type UserStatusUpdateInput,
  type UserUpdateFormInput,
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

function normalizeNullableText(value: unknown) {
  return typeof value === 'string' ? value : null
}

function normalizeUserStatus(value: unknown): 0 | 1 {
  return Number(value ?? 1) === 0 ? 0 : 1
}

function normalizeUserSex(value: unknown): 0 | 1 | 2 {
  const parsed = Number(value ?? 0)
  if (parsed === 1 || parsed === 2) {
    return parsed
  }
  return 0
}

function normalizeUser(input: unknown): User {
  const record = getRecord(input)

  return {
    id: toId(record.id),
    username: String(record.username ?? ''),
    nickname: String(record.nickname ?? ''),
    deptName: normalizeNullableText(record.deptName),
    email: normalizeNullableText(record.email),
    phone: normalizeNullableText(record.phone),
    sex: normalizeUserSex(record.sex),
    status: normalizeUserStatus(record.status),
    loginIp: normalizeNullableText(record.loginIp),
    loginDate: normalizeNullableText(record.loginDate),
    remark: normalizeNullableText(record.remark),
    createTime: normalizeNullableText(record.createTime),
  }
}

function normalizeUserEditDetail(input: unknown): UserEditDetail {
  const record = getRecord(input)

  return {
    id: toId(record.id),
    version: toId(record.version),
    username: String(record.username ?? ''),
    nickname: String(record.nickname ?? ''),
    email: normalizeNullableText(record.email),
    phone: normalizeNullableText(record.phone),
    sex: normalizeUserSex(record.sex),
    deptId:
      record.deptId === null || record.deptId === undefined
        ? null
        : toId(record.deptId),
    deptName: normalizeNullableText(record.deptName),
    status: normalizeUserStatus(record.status),
    remark: normalizeNullableText(record.remark),
    loginIp: normalizeNullableText(record.loginIp),
    loginDate: normalizeNullableText(record.loginDate),
    createTime: normalizeNullableText(record.createTime),
  }
}

function normalizeRoleOption(input: unknown): UserRoleOption {
  const record = getRecord(input)

  return {
    id: toId(record.id),
    roleName: String(record.roleName ?? ''),
    roleKey: String(record.roleKey ?? ''),
    status: Number(record.status ?? 1),
  }
}

function normalizeDeptTreeNode(
  input: unknown,
  seen: Set<string>,
  parentId: string = '0'
): DeptTreeNode[] {
  const record = getRecord(input)
  const deptId = toId(record.id ?? record.deptId)
  const childrenSource = Array.isArray(record.children) ? record.children : []

  if (!deptId || deptId === '0') {
    return childrenSource.flatMap((child) =>
      normalizeDeptTreeNode(child, seen, parentId)
    )
  }

  if (seen.has(deptId)) {
    return []
  }

  seen.add(deptId)

  return [
    {
      id: deptId,
      label: String(record.label ?? record.deptName ?? ''),
      children: childrenSource.flatMap((child) =>
        normalizeDeptTreeNode(child, seen, deptId)
      ),
    },
  ]
}

export async function fetchUsers(search: Partial<UserManagementSearch>) {
  const response = await apiClient.get<ApiResult<PagedResult<unknown>>>(
    '/system/user/list',
    {
      params: buildUserListQuery(search),
    }
  )

  const page = unwrapResult(response.data)
  return {
    pageNum: Number(page.pageNum ?? 1),
    pageSize: Number(page.pageSize ?? 10),
    total: Number(page.total ?? 0),
    pages: Number(page.pages ?? 0),
    records: (page.records ?? []).map(normalizeUser),
  } satisfies PagedResult<User>
}

export async function fetchUserRoleIds(userId: string) {
  const response = await apiClient.get<ApiResult<unknown>>(
    `/system/user/${userId}/roles`
  )

  return toIdList(unwrapResult(response.data))
}

export async function fetchUserDetail(userId: string) {
  const response = await apiClient.get<ApiResult<unknown>>(
    `/system/user/${userId}`
  )

  return normalizeUserEditDetail(unwrapResult(response.data))
}

export async function fetchAllRoles() {
  const response = await apiClient.get<ApiResult<unknown[]>>('/system/role/all')

  return unwrapResult(response.data).map(normalizeRoleOption)
}

export async function fetchDeptTree() {
  const response = await apiClient.get<ApiResult<unknown[]>>(
    '/system/dept/treeselect'
  )

  const seen = new Set<string>()
  return unwrapResult(response.data).flatMap((node) =>
    normalizeDeptTreeNode(node, seen)
  )
}

export async function createUser(input: UserCreateFormInput) {
  const response = await apiClient.post<ApiResult<number | string>>(
    '/system/user',
    buildUserCreatePayload(input)
  )

  return toId(unwrapResult(response.data))
}

export async function updateUser(input: UserUpdateFormInput) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/user',
    buildUserUpdatePayload(input)
  )

  return unwrapResult(response.data)
}

export async function deleteUsers(userIds: string[]) {
  const response = await apiClient.delete<ApiResult<null>>(
    `/system/user/${userIds.join(',')}`
  )

  return unwrapResult(response.data)
}

export async function changeUserStatus(input: UserStatusUpdateInput) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/user/changeStatus',
    buildUserStatusPayload(input)
  )

  return unwrapResult(response.data)
}

export async function resetUserPassword(input: ResetPasswordFormInput) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/user/resetPwd',
    buildResetPasswordPayload(input)
  )

  return unwrapResult(response.data)
}
