import { ShieldPlus } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { Button } from '@/components/ui/button'
import { getRoleManagementAccess } from '../role-management-access'
import { useRoles } from './roles-provider'

export function RolesPrimaryButtons() {
  const { setOpen } = useRoles()
  const authUser = useAuthStore((state) => state.user)
  const { canCreateRoles } = getRoleManagementAccess(authUser)

  if (!canCreateRoles) {
    return null
  }

  return (
    <Button className='space-x-1' onClick={() => setOpen('add')}>
      <span>新建角色</span> <ShieldPlus size={18} />
    </Button>
  )
}
