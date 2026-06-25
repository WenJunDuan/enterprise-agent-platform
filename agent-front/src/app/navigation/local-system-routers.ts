import type { BackendMenuRouter } from './types'

export const localSystemMenuRouters: BackendMenuRouter[] = [
  {
    name: 'System',
    path: '/system',
    meta: {
      title: '系统管理',
    },
    children: [
      {
        name: 'SystemUser',
        path: 'user',
        component: 'system/user/index',
        meta: {
          title: '用户管理',
        },
      },
      {
        name: 'SystemRole',
        path: 'role',
        component: 'system/role/index',
        meta: {
          title: '角色管理',
        },
      },
      {
        name: 'SystemMenu',
        path: 'menu',
        component: 'system/menu/index',
        meta: {
          title: '菜单管理',
        },
      },
      {
        name: 'SystemDept',
        path: 'dept',
        component: 'system/dept/index',
        meta: {
          title: '部门管理',
        },
      },
      {
        name: 'SystemDict',
        path: 'dict',
        component: 'system/dict/index',
        meta: {
          title: '字典管理',
        },
      },
      {
        name: 'SystemFile',
        path: 'file',
        component: 'system/file/index',
        meta: {
          title: '文件管理',
        },
      },
    ],
  },
]

export function cloneLocalSystemMenuRouters() {
  return JSON.parse(JSON.stringify(localSystemMenuRouters)) as BackendMenuRouter[]
}
