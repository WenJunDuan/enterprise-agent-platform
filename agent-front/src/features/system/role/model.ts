import { toId, toIdList } from '@/lib/ids'

export type RoleStatus = 0 | 1
export type RoleStatusFilter = 'active' | 'inactive'
export type RoleDataScope = 1 | 2 | 3 | 4 | 5

export type Role = {
  id: string
  roleName: string
  roleKey: string
  orderNum: number
  dataScope: RoleDataScope
  status: RoleStatus
  remark: string | null
  createTime: string | null
}

export type RoleDetail = Role

export type PagedResult<T> = {
  pageNum: number
  pageSize: number
  total: number
  pages: number
  records: T[]
}

export type RoleManagementSearch = {
  page: number
  pageSize: number
  roleName: string
  roleKey: string
  status: RoleStatusFilter[]
}

export type RoleListQuery = {
  pageNum: number
  pageSize: number
  roleName?: string
  roleKey?: string
  status?: 0 | 1
}

export type RoleCreateFormInput = {
  roleName: string
  roleKey: string
  orderNum: string
  dataScope: string
  status: string
  remark: string
  menuIds: string[]
  deptIds: string[]
}

export type RoleUpdateFormInput = RoleCreateFormInput & {
  id: string
}

export type RoleStatusUpdateInput = {
  roleId: string
  status: 0 | 1
}

export type RoleDataScopeUpdateInput = {
  roleId: string
  dataScope: RoleDataScope
  deptIds: string[]
}

function trimOrEmpty(value?: string | null) {
  return value?.trim() ?? ''
}

function toBackendStatus(status?: RoleStatusFilter) {
  if (status === 'active') {
    return 1
  }

  if (status === 'inactive') {
    return 0
  }

  return undefined
}


export function buildRoleListQuery(
  search: Partial<RoleManagementSearch>
): RoleListQuery {
  const roleName = trimOrEmpty(search.roleName)
  const roleKey = trimOrEmpty(search.roleKey)
  const status = toBackendStatus(search.status?.[0])

  return {
    pageNum: search.page ?? 1,
    pageSize: search.pageSize ?? 10,
    roleName: roleName || undefined,
    roleKey: roleKey || undefined,
    status,
  }
}

function buildRoleBasePayload(input: RoleCreateFormInput) {
  return {
    roleName: trimOrEmpty(input.roleName),
    roleKey: trimOrEmpty(input.roleKey),
    orderNum: Number(trimOrEmpty(input.orderNum) || '0'),
    dataScope: Number(input.dataScope),
    status: Number(input.status),
    remark: trimOrEmpty(input.remark) || null,
    menuIds: toIdList(input.menuIds),
    deptIds: toIdList(input.deptIds),
  }
}

export function buildRoleCreatePayload(input: RoleCreateFormInput) {
  return buildRoleBasePayload(input)
}

export function buildRoleUpdatePayload(input: RoleUpdateFormInput) {
  return {
    id: toId(input.id),
    ...buildRoleBasePayload(input),
  }
}

export const roleDataScopeOptions: Array<{
  label: string
  value: `${RoleDataScope}`
  tone: string
}> = [
  { label: '全部数据', value: '1', tone: 'border-sky-300 text-sky-700' },
  { label: '本部门数据', value: '2', tone: 'border-blue-300 text-blue-700' },
  {
    label: '本部门及子部门',
    value: '3',
    tone: 'border-indigo-300 text-indigo-700',
  },
  {
    label: '自定义部门',
    value: '4',
    tone: 'border-amber-300 text-amber-700',
  },
  { label: '仅本人', value: '5', tone: 'border-rose-300 text-rose-700' },
]

export function getRoleDataScopeLabel(value: RoleDataScope) {
  return (
    roleDataScopeOptions.find((option) => option.value === String(value))
      ?.label ?? '未知'
  )
}

export function getRoleDataScopeTone(value: RoleDataScope) {
  return (
    roleDataScopeOptions.find((option) => option.value === String(value))
      ?.tone ?? 'border-muted-foreground/30 text-muted-foreground'
  )
}
