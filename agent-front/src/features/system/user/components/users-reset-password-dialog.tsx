import { useEffect } from 'react'
import { z } from 'zod'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { PasswordInput } from '@/components/password-input'
import { fetchUserDetail, resetUserPassword } from '../api'
import { type User } from '../data/schema'

const resetPasswordSchema = z
  .object({
    userId: z.string(),
    version: z.string().nullable(),
    password: z
      .string()
      .min(8, '密码长度至少为 8 位。')
      .max(20, '密码长度不能超过 20 位。')
      .regex(/[a-z]/, '密码至少包含一个小写字母。')
      .regex(/\d/, '密码至少包含一个数字。'),
    confirmPassword: z.string().min(1, '请再次输入新密码。'),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: '两次输入的新密码不一致。',
    path: ['confirmPassword'],
  })

type ResetPasswordForm = z.infer<typeof resetPasswordSchema>

type UsersResetPasswordDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentRow: User
}

export function UsersResetPasswordDialog({
  open,
  onOpenChange,
  currentRow,
}: UsersResetPasswordDialogProps) {
  const queryClient = useQueryClient()
  const form = useForm<ResetPasswordForm>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: {
      userId: currentRow.id,
      version: null,
      password: '',
      confirmPassword: '',
    },
  })

  const detailQuery = useQuery({
    queryKey: ['system', 'users', 'detail', currentRow.id],
    queryFn: () => fetchUserDetail(currentRow.id),
    enabled: open,
    staleTime: 0,
  })

  useEffect(() => {
    form.reset({
      userId: currentRow.id,
      version: detailQuery.data?.version ?? null,
      password: '',
      confirmPassword: '',
    })
  }, [currentRow.id, detailQuery.data?.version, form, open])

  const mutation = useMutation({
    mutationFn: resetUserPassword,
    onSuccess: async () => {
      toast.success(`用户“${currentRow.username}”的密码已重置。`)
      form.reset()
      onOpenChange(false)
      await queryClient.invalidateQueries({
        queryKey: ['system', 'users', 'detail', currentRow.id],
      })
    },
  })

  const isDetailLoading = detailQuery.isFetching || !detailQuery.data
  const hasDetailError = detailQuery.isError

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        form.reset()
        onOpenChange(nextOpen)
      }}
    >
      <DialogContent className='sm:max-w-md'>
        <DialogHeader className='text-start'>
          <DialogTitle>重置密码</DialogTitle>
          <DialogDescription>
            {hasDetailError
              ? '用户详情加载失败，请关闭弹窗后重试。'
              : `为用户“${currentRow.username}”设置新的登录密码。提交后该用户需要使用新密码重新登录。`}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            id='user-reset-password-form'
            onSubmit={form.handleSubmit((values) => {
              if (values.version === null) {
                return
              }

              mutation.mutate({
                ...values,
                version: values.version,
              })
            })}
            className='space-y-4'
          >
            <FormField
              control={form.control}
              name='password'
              render={({ field }) => (
                <FormItem>
                  <FormLabel>新密码</FormLabel>
                  <FormControl>
                    <PasswordInput placeholder='请输入新密码' {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name='confirmPassword'
              render={({ field }) => (
                <FormItem>
                  <FormLabel>确认新密码</FormLabel>
                  <FormControl>
                    <PasswordInput placeholder='请再次输入新密码' {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>

        <DialogFooter>
          <Button
            type='submit'
            form='user-reset-password-form'
            disabled={mutation.isPending || isDetailLoading || hasDetailError}
          >
            保存新密码
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
