export interface AuthUser {
  id: string
  version?: string
  username: string
  nickname: string
  email?: string
  phone?: string
  avatar?: string
  sex?: number
  deptName?: string
  status?: number
  loginIp?: string
  loginLocation?: string
  loginDate?: string
  remark?: string
  createTime?: string
  roles: string[]
  permissions: string[]
}

export type BootstrapStatus = 'idle' | 'loading' | 'ready'
