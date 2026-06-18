import { hasPermission } from '@/app/auth/access'
import type { AuthUser } from '@/types/auth'

type UserPermissionSubject =
  | Pick<AuthUser, 'roles' | 'permissions'>
  | null
  | undefined

export type UserManagementAccess = {
  canCreateUsers: boolean
  canEditUsers: boolean
  canChangeUserStatus: boolean
  canResetPasswords: boolean
  canDeleteUsers: boolean
  canBulkDeleteUsers: boolean
  hasRowActions: boolean
}

export function getUserManagementAccess(
  user: UserPermissionSubject
): UserManagementAccess {
  const canCreateUsers =
    hasPermission(user, 'system:user:add') &&
    hasPermission(user, 'system:role:query') &&
    hasPermission(user, 'system:dept:treeselect')
  const canEditUsers =
    hasPermission(user, 'system:user:edit') &&
    hasPermission(user, 'system:user:query') &&
    hasPermission(user, 'system:role:query') &&
    hasPermission(user, 'system:dept:treeselect')
  const canChangeUserStatus =
    hasPermission(user, 'system:user:edit') &&
    hasPermission(user, 'system:user:query')
  const canResetPasswords =
    hasPermission(user, 'system:user:resetPwd') &&
    hasPermission(user, 'system:user:query')
  const canDeleteUsers = hasPermission(user, 'system:user:remove')

  return {
    canCreateUsers,
    canEditUsers,
    canChangeUserStatus,
    canResetPasswords,
    canDeleteUsers,
    canBulkDeleteUsers: canDeleteUsers,
    hasRowActions:
      canEditUsers || canChangeUserStatus || canResetPasswords || canDeleteUsers,
  }
}
