import type { CheckableTreeNode } from './components/roles-checkable-tree'
import type {
  PagedResult,
  Role,
  RoleCreateFormInput,
  RoleDataScopeUpdateInput,
  RoleDetail,
  RoleManagementSearch,
  RoleStatusUpdateInput,
  RoleUpdateFormInput,
} from './model'

const localRoles: Role[] = [
  {
    id: '1',
    roleName: '管理员',
    roleKey: 'admin',
    orderNum: 0,
    dataScope: 1,
    status: 1,
    remark: '本地 JSON 数据',
    createTime: '2026-06-25 00:00:00',
  },
  {
    id: '2',
    roleName: '评审员',
    roleKey: 'reviewer',
    orderNum: 1,
    dataScope: 2,
    status: 1,
    remark: '本地 JSON 数据',
    createTime: '2026-06-25 00:00:00',
  },
]

const localMenuTree: CheckableTreeNode[] = [
  {
    id: '100',
    label: '系统管理',
    children: [
      { id: '101', label: '用户管理', children: [] },
      { id: '102', label: '角色管理', children: [] },
      { id: '103', label: '菜单管理', children: [] },
      { id: '104', label: '部门管理', children: [] },
      { id: '105', label: '字典管理', children: [] },
      { id: '106', label: '文件管理', children: [] },
    ],
  },
]

const localDeptTree: CheckableTreeNode[] = [
  {
    id: '100',
    label: '管理中心',
    children: [{ id: '101', label: '评审部', children: [] }],
  },
]

function paginate<T>(records: T[], page = 1, pageSize = 10): PagedResult<T> {
  const safePage = Math.max(page, 1)
  const safePageSize = Math.max(pageSize, 1)
  const start = (safePage - 1) * safePageSize

  return {
    pageNum: safePage,
    pageSize: safePageSize,
    total: records.length,
    pages: Math.max(Math.ceil(records.length / safePageSize), 1),
    records: records.slice(start, start + safePageSize),
  }
}

export async function fetchRoles(search: Partial<RoleManagementSearch>) {
  const records = localRoles.filter((role) => {
    const status = search.status?.[0]

    return (
      (!search.roleName?.trim() || role.roleName.includes(search.roleName)) &&
      (!search.roleKey?.trim() || role.roleKey.includes(search.roleKey)) &&
      (!status ||
        (status === 'active' ? role.status === 1 : role.status === 0))
    )
  })

  return paginate(records, search.page, search.pageSize)
}

export async function fetchRoleDetail(roleId: string) {
  return (localRoles.find((role) => role.id === roleId) ??
    localRoles[0]) as RoleDetail
}

export async function fetchRoleMenuIds(roleId: string) {
  return roleId === '1'
    ? ['100', '101', '102', '103', '104', '105', '106']
    : ['103']
}

export async function fetchRoleDeptIds(_roleId: string) {
  return ['100']
}

export async function createRole(_input: RoleCreateFormInput) {
  return String(localRoles.length + 1)
}

export async function updateRole(_input: RoleUpdateFormInput) {
  return null
}

export async function deleteRoles(_roleIds: string[]) {
  return null
}

export async function changeRoleStatus(_input: RoleStatusUpdateInput) {
  return null
}

export async function fetchMenuTreeSelect() {
  return localMenuTree
}

export async function fetchDeptTreeSelect() {
  return localDeptTree
}

export async function updateRoleDataScope(_input: RoleDataScopeUpdateInput) {
  return null
}
