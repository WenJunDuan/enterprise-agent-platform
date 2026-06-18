import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { changeUserStatus, fetchUserDetail } from '../api'
import { type User } from '../data/schema'

type UsersStatusDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentRow: User
}

export function UsersStatusDialog({
  open,
  onOpenChange,
  currentRow,
}: UsersStatusDialogProps) {
  const queryClient = useQueryClient()
  const nextStatus = currentRow.status === 1 ? 0 : 1
  const actionLabel = nextStatus === 1 ? '启用' : '停用'

  const detailQuery = useQuery({
    queryKey: ['system', 'users', 'detail', currentRow.id],
    queryFn: () => fetchUserDetail(currentRow.id),
    enabled: open,
    staleTime: 0,
  })

  const mutation = useMutation({
    mutationFn: changeUserStatus,
    onSuccess: async () => {
      toast.success(`已${actionLabel}用户“${currentRow.username}”。`)
      onOpenChange(false)
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ['system', 'users', 'list'],
        }),
        queryClient.invalidateQueries({
          queryKey: ['system', 'users', 'detail', currentRow.id],
        }),
      ])
    },
  })

  const handleConfirm = () => {
    if (!detailQuery.data) {
      return
    }

    mutation.mutate({
      userId: currentRow.id,
      version: detailQuery.data.version,
      status: nextStatus,
    })
  }

  const isDetailLoading = detailQuery.isFetching || !detailQuery.data
  const hasDetailError = detailQuery.isError

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      handleConfirm={handleConfirm}
      disabled={isDetailLoading || hasDetailError}
      isLoading={mutation.isPending || detailQuery.isFetching}
      title={
        <span className='text-foreground'>
          <AlertTriangle className='me-1 inline-block size-4' />
          {actionLabel}用户
        </span>
      }
      desc={
        hasDetailError
          ? '用户详情加载失败，请关闭后重试。'
          : `确认${actionLabel}用户“${currentRow.username}”吗？该操作会立即影响该账号后续登录和使用状态。`
      }
      confirmText={actionLabel}
      destructive={nextStatus === 0}
    />
  )
}
