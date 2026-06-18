import { toId, toIdList } from '@/lib/ids'

export type UserStatusFilter = 'active' | 'inactive'
export type UserSexFilter = '0' | '1' | '2'

export type UserManagementSearch = {
  page: number
  pageSize: number
  username: string
  nickname: string
  email: string
  phone: string
  sex: UserSexFilter[]
  status: UserStatusFilter[]
}

export type TreeOption = {
  id: string
  label: string
  children: TreeOption[]
}

export type FlattenOption = {
  label: string
  value: string
}

export type UserListQuery = {
  pageNum: number
  pageSize: number
  username?: string
  nickname?: string
  email?: string
  phone?: string
  sex?: 0 | 1 | 2
  status?: 0 | 1
}

export type UserCreateFormInput = {
  username: string
  nickname: string
  phone: string
  email: string
  sex: string
  deptId: string
  status: string
  roleIds: string[]
  remark: string
  password: string
}

export type UserUpdateFormInput = {
  id: string
  version: string
  username: string
  nickname: string
  phone: string
  email: string
  sex: string
  deptId: string
  status: string
  roleIds: string[]
  remark: string
}

export type ResetPasswordFormInput = {
  userId: string
  version: string
  password: string
}

export type UserStatusUpdateInput = {
  userId: string
  version: string
  status: 0 | 1
}

function trimOrEmpty(value?: string | null) {
  return value?.trim() ?? ''
}

function toBackendStatus(status?: UserStatusFilter) {
  if (status === 'active') {
    return 1
  }

  if (status === 'inactive') {
    return 0
  }

  return undefined
}

function toBackendSex(sex?: UserSexFilter) {
  if (sex === '0' || sex === '1' || sex === '2') {
    return Number(sex) as 0 | 1 | 2
  }

  return undefined
}

export function buildUserListQuery(
  search: Partial<UserManagementSearch>
): UserListQuery {
  const username = trimOrEmpty(search.username)
  const nickname = trimOrEmpty(search.nickname)
  const email = trimOrEmpty(search.email)
  const phone = trimOrEmpty(search.phone)
  const sex = toBackendSex(search.sex?.[0])
  const status = toBackendStatus(search.status?.[0])

  return {
    pageNum: search.page ?? 1,
    pageSize: search.pageSize ?? 10,
    username: username || undefined,
    nickname: nickname || undefined,
    email: email || undefined,
    phone: phone || undefined,
    sex,
    status,
  }
}

export function buildUserCreatePayload(input: UserCreateFormInput) {
  return {
    username: trimOrEmpty(input.username),
    password: trimOrEmpty(input.password),
    nickname: trimOrEmpty(input.nickname),
    phone: trimOrEmpty(input.phone),
    email: trimOrEmpty(input.email),
    sex: Number(input.sex),
    deptId: toId(input.deptId),
    status: Number(input.status),
    roleIds: toIdList(input.roleIds),
    remark: input.remark.trim(),
  }
}

export function buildUserUpdatePayload(input: UserUpdateFormInput) {
  return {
    id: toId(input.id),
    version: toId(input.version),
    username: trimOrEmpty(input.username),
    nickname: trimOrEmpty(input.nickname),
    phone: trimOrEmpty(input.phone),
    email: trimOrEmpty(input.email),
    sex: Number(input.sex),
    deptId: toId(input.deptId),
    status: Number(input.status),
    roleIds: toIdList(input.roleIds),
    remark: input.remark.trim(),
  }
}

export function buildResetPasswordPayload(input: ResetPasswordFormInput) {
  return {
    userId: toId(input.userId),
    version: toId(input.version),
    password: trimOrEmpty(input.password),
  }
}

export function buildUserStatusPayload(input: UserStatusUpdateInput) {
  return {
    userId: toId(input.userId),
    version: toId(input.version),
    status: input.status,
  }
}

export function flattenDeptOptions(
  options: TreeOption[],
  depth: number = 0,
  seen: Set<string> = new Set()
): FlattenOption[] {
  return options.flatMap((option) => {
    if (seen.has(option.id)) {
      return []
    }

    seen.add(option.id)
    const prefix = depth > 0 ? `${'\u00A0\u00A0'.repeat(depth - 1)}└─ ` : ''
    return [
      {
        label: `${prefix}${option.label}`,
        value: option.id,
      },
      ...flattenDeptOptions(option.children, depth + 1, seen),
    ]
  })
}
