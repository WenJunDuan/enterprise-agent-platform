import { hasPermission } from '@/app/auth/access'
import type { AuthUser } from '@/types/auth'

type RolePermissionSubject =
  | Pick<AuthUser, 'roles' | 'permissions'>
  | null
  | undefined

export type RoleManagementAccess = {
  canCreateRoles: boolean
  canEditRoles: boolean
  canChangeRoleStatus: boolean
  canChangeRoleDataScope: boolean
  canDeleteRoles: boolean
  canBulkDeleteRoles: boolean
  hasRowActions: boolean
}

const SUPER_ADMIN_ROLE_ID = '1'

export function getRoleManagementAccess(
  user: RolePermissionSubject
): RoleManagementAccess {
  const canCreateRoles =
    hasPermission(user, 'system:role:add') &&
    hasPermission(user, 'system:menu:treeselect')
  const canEditRoles =
    hasPermission(user, 'system:role:edit') &&
    hasPermission(user, 'system:role:query') &&
    hasPermission(user, 'system:menu:treeselect')
  const canChangeRoleStatus =
    hasPermission(user, 'system:role:edit') &&
    hasPermission(user, 'system:role:query')
  const canChangeRoleDataScope =
    hasPermission(user, 'system:role:edit') &&
    hasPermission(user, 'system:dept:treeselect')
  const canDeleteRoles = hasPermission(user, 'system:role:remove')

  return {
    canCreateRoles,
    canEditRoles,
    canChangeRoleStatus,
    canChangeRoleDataScope,
    canDeleteRoles,
    canBulkDeleteRoles: canDeleteRoles,
    hasRowActions:
      canEditRoles ||
      canChangeRoleStatus ||
      canChangeRoleDataScope ||
      canDeleteRoles,
  }
}

export function isProtectedSystemRole(roleId: string) {
  return roleId === SUPER_ADMIN_ROLE_ID
}
