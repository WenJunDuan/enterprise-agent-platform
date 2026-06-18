import { redirect } from '@tanstack/react-router'
import { useAuthStore } from '@/stores/auth-store'
import type { AuthUser } from '@/types/auth'

const SUPER_ADMIN_ROLE = 'admin'
const SUPER_ADMIN_PERMISSION = '*:*:*'

type AccessRequirement = {
  permissions?: string[]
  roles?: string[]
}

type RouteAccessRequirement = AccessRequirement & {
  locationHref: string
  message?: string
}

function includesValue(values: string[] | undefined, expected: string) {
  return Boolean(values?.includes(expected))
}

export function hasRole(
  user: Pick<AuthUser, 'roles'> | null | undefined,
  role: string
) {
  if (!user) {
    return false
  }

  return (
    includesValue(user.roles, SUPER_ADMIN_ROLE) || includesValue(user.roles, role)
  )
}

export function hasAnyRole(
  user: Pick<AuthUser, 'roles'> | null | undefined,
  roles: string[]
) {
  if (!roles.length) {
    return true
  }

  return roles.some((role) => hasRole(user, role))
}

export function hasPermission(
  user: Pick<AuthUser, 'roles' | 'permissions'> | null | undefined,
  permission: string
) {
  if (!user) {
    return false
  }

  return (
    includesValue(user.roles, SUPER_ADMIN_ROLE) ||
    includesValue(user.permissions, SUPER_ADMIN_PERMISSION) ||
    includesValue(user.permissions, permission)
  )
}

export function hasAnyPermission(
  user: Pick<AuthUser, 'roles' | 'permissions'> | null | undefined,
  permissions: string[]
) {
  if (!permissions.length) {
    return true
  }

  return permissions.some((permission) => hasPermission(user, permission))
}

export function hasAccess(
  user: Pick<AuthUser, 'roles' | 'permissions'> | null | undefined,
  requirement: AccessRequirement
) {
  const permissionPass = hasAnyPermission(user, requirement.permissions ?? [])
  const rolePass = hasAnyRole(user, requirement.roles ?? [])

  return permissionPass && rolePass
}

export function useAccess(requirement: AccessRequirement) {
  const user = useAuthStore((state) => state.user)

  return hasAccess(user, requirement)
}

export function ensureRouteAccess(requirement: RouteAccessRequirement) {
  const user = useAuthStore.getState().user
  if (!user) {
    return
  }

  if (hasAccess(user, requirement)) {
    return
  }

  throw redirect({
    to: '/403',
    search: {
      redirect: requirement.locationHref,
      message: requirement.message,
    },
  })
}
