export type UserStatus = 0 | 1
export type UserSex = 0 | 1 | 2

export type User = {
  id: string
  username: string
  nickname: string
  deptName: string | null
  email: string | null
  phone: string | null
  sex: UserSex
  status: UserStatus
  loginIp: string | null
  loginDate: string | null
  remark: string | null
  createTime: string | null
}

export type UserEditDetail = {
  id: string
  version: string
  username: string
  nickname: string
  email: string | null
  phone: string | null
  sex: UserSex
  deptId: string | null
  deptName: string | null
  status: UserStatus
  remark: string | null
  loginIp: string | null
  loginDate: string | null
  createTime: string | null
}

export type PagedResult<T> = {
  pageNum: number
  pageSize: number
  total: number
  pages: number
  records: T[]
}

export type UserRoleOption = {
  id: string
  roleName: string
  roleKey: string
  status: number
}

export type DeptTreeNode = {
  id: string
  label: string
  children: DeptTreeNode[]
}
