import { UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth-store'
import { getUserManagementAccess } from '../user-management-access'
import { useUsers } from './users-provider'

export function UsersPrimaryButtons() {
  const { setOpen } = useUsers()
  const authUser = useAuthStore((state) => state.user)
  const { canCreateUsers } = getUserManagementAccess(authUser)

  if (!canCreateUsers) {
    return null
  }

  return (
    <Button className='space-x-1' onClick={() => setOpen('add')}>
      <span>新建用户</span> <UserPlus size={18} />
    </Button>
  )
}
