import { toId } from '@/lib/ids'
import type {
  DeptTreeNode,
  PagedResult,
  User,
  UserEditDetail,
  UserRoleOption,
} from './data/schema'
import type {
  ResetPasswordFormInput,
  UserCreateFormInput,
  UserManagementSearch,
  UserStatusUpdateInput,
  UserUpdateFormInput,
} from './model'

const localUsers: UserEditDetail[] = [
  {
    id: '1',
    version: '1',
    username: 'admin',
    nickname: '系统管理员',
    deptId: '100',
    deptName: '管理中心',
    email: 'admin@example.com',
    phone: '13800000000',
    sex: 0,
    status: 1,
    loginIp: '127.0.0.1',
    loginDate: '2026-06-25 09:00:00',
    remark: '本地 JSON 数据',
    createTime: '2026-06-25 00:00:00',
  },
  {
    id: '2',
    version: '1',
    username: 'reviewer',
    nickname: '评审人员',
    deptId: '101',
    deptName: '评审部',
    email: 'reviewer@example.com',
    phone: '13900000000',
    sex: 0,
    status: 1,
    loginIp: null,
    loginDate: null,
    remark: '本地 JSON 数据',
    createTime: '2026-06-25 00:00:00',
  },
]

const localRoles: UserRoleOption[] = [
  { id: '1', roleName: '管理员', roleKey: 'admin', status: 1 },
  { id: '2', roleName: '评审员', roleKey: 'reviewer', status: 1 },
]

const localDeptTree: DeptTreeNode[] = [
  {
    id: '100',
    label: '管理中心',
    children: [
      {
        id: '101',
        label: '评审部',
        children: [],
      },
    ],
  },
]

function toUser(detail: UserEditDetail): User {
  return {
    id: detail.id,
    username: detail.username,
    nickname: detail.nickname,
    deptName: detail.deptName,
    email: detail.email,
    phone: detail.phone,
    sex: detail.sex,
    status: detail.status,
    loginIp: detail.loginIp,
    loginDate: detail.loginDate,
    remark: detail.remark,
    createTime: detail.createTime,
  }
}

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

function includesText(value: string | null, keyword?: string) {
  return !keyword?.trim() || value?.includes(keyword.trim())
}

export async function fetchUsers(search: Partial<UserManagementSearch>) {
  const records = localUsers.map(toUser).filter((user) => {
    const status = search.status?.[0]
    const sex = search.sex?.[0]

    return (
      includesText(user.username, search.username) &&
      includesText(user.nickname, search.nickname) &&
      includesText(user.email, search.email) &&
      includesText(user.phone, search.phone) &&
      (!status ||
        (status === 'active' ? user.status === 1 : user.status === 0)) &&
      (!sex || String(user.sex) === sex)
    )
  })

  return paginate(records, search.page, search.pageSize)
}

export async function fetchUserRoleIds(userId: string) {
  return userId === '1' ? ['1'] : ['2']
}

export async function fetchUserDetail(userId: string) {
  return (
    localUsers.find((user) => user.id === userId) ??
    localUsers[0] ?? {
      id: toId(userId),
      version: '1',
      username: '',
      nickname: '',
      email: null,
      phone: null,
      sex: 0,
      deptId: null,
      deptName: null,
      status: 1,
      remark: null,
      loginIp: null,
      loginDate: null,
      createTime: null,
    }
  )
}

export async function fetchAllRoles() {
  return localRoles
}

export async function fetchDeptTree() {
  return localDeptTree
}

export async function createUser(_input: UserCreateFormInput) {
  return String(localUsers.length + 1)
}

export async function updateUser(_input: UserUpdateFormInput) {
  return null
}

export async function deleteUsers(_userIds: string[]) {
  return null
}

export async function changeUserStatus(_input: UserStatusUpdateInput) {
  return null
}

export async function resetUserPassword(_input: ResetPasswordFormInput) {
  return null
}
