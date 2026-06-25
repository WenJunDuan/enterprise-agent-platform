import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth-store'
import { REQUIRE_ADMIN_AUTH } from '@/config/app'
import { navigationQueryOptions } from './api'
import { useNavigationMenuVisibility } from './menu-visibility'
import { buildNavigationGroups, buildNavigationUser } from './registry'

export function useNavigation() {
  const user = useAuthStore((state) => state.user)
  const menuVisibility = useNavigationMenuVisibility()
  const menuQuery = useQuery({
    ...navigationQueryOptions(),
    enabled: REQUIRE_ADMIN_AUTH && Boolean(user),
  })

  return {
    user: buildNavigationUser(user),
    menuRouters: menuQuery.data,
    navGroups: buildNavigationGroups(user, menuQuery.data, menuVisibility),
    menuQuery,
  }
}
