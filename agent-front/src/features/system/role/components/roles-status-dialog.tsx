import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { handleServerError } from '@/lib/handle-server-error'
import { changeRoleStatus } from '../api'
import { type Role } from '../model'

type RolesStatusDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentRow: Role
}

export function RolesStatusDialog({
  open,
  onOpenChange,
  currentRow,
}: RolesStatusDialogProps) {
  const queryClient = useQueryClient()
  const nextStatus = currentRow.status === 1 ? 0 : 1
  const actionLabel = nextStatus === 1 ? '启用' : '停用'

  const mutation = useMutation({
    mutationFn: changeRoleStatus,
    onSuccess: async () => {
      toast.success(`已${actionLabel}角色“${currentRow.roleName}”。`)
      onOpenChange(false)
      await queryClient.invalidateQueries({
        queryKey: ['system', 'role', 'list'],
      })
    },
    onError: handleServerError,
  })

  const handleConfirm = () => {
    mutation.mutate({
      roleId: currentRow.id,
      status: nextStatus,
    })
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      handleConfirm={handleConfirm}
      isLoading={mutation.isPending}
      title={
        <span className='text-foreground'>
          <AlertTriangle className='me-1 inline-block size-4' />
          {actionLabel}角色
        </span>
      }
      desc={`确认${actionLabel}角色“${currentRow.roleName}”吗？该操作会立即影响绑定此角色的用户。`}
      confirmText={actionLabel}
      destructive={nextStatus === 0}
    />
  )
}
