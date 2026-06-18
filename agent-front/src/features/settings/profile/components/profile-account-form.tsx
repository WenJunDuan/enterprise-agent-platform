import { useEffect, useState } from 'react'
import { z } from 'zod'
import { AxiosError } from 'axios'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchCurrentUser, updateProfile } from '@/app/auth/api'
import type { ApiResult } from '@/types/api'
import {
  Building2,
  CalendarClock,
  Mail,
  MapPin,
  Network,
  PencilLine,
  Phone,
  Save,
  UserCircle2,
  UserRound,
  VenusAndMars,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/auth-store'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { extractProfileServerErrors } from '../profile-account-form-errors'
import {
  buildProfileFormValues,
  buildProfileUpdatePayload,
  type ProfileFormValues,
} from '../profile-account-model'
import {
  formatDateTime,
  formatText,
  formatUserSex,
  formatUserStatus,
} from '../profile-view-model'

const phonePattern = /^$|^1[3-9]\d{9}$/
const emailPattern = /^$|^[^\s@]+@[^\s@]+\.[^\s@]+$/

const profileFormSchema = z.object({
  nickname: z
    .string()
    .min(1, '请输入昵称。')
    .max(10, '昵称长度不能超过 10 个字符。'),
  email: z
    .string()
    .refine((value) => emailPattern.test(value), '邮箱格式不正确。'),
  phone: z
    .string()
    .refine((value) => phonePattern.test(value), '手机号格式不正确。'),
  sex: z.enum(['0', '1', '2']),
  remark: z.string().max(500, '备注长度不能超过 500 个字符。'),
})

function ProfileSkeleton() {
  return (
    <div className='space-y-6'>
      <Card>
        <CardHeader className='gap-5 md:grid-cols-[auto_1fr_auto] md:items-center'>
          <Skeleton className='h-20 w-20 rounded-full' />
          <div className='space-y-3'>
            <div className='flex gap-3'>
              <Skeleton className='h-10 w-40' />
              <Skeleton className='h-7 w-20 rounded-full' />
            </div>
            <Skeleton className='h-4 w-40' />
            <Skeleton className='h-4 w-44' />
          </div>
          <Skeleton className='h-9 w-28 rounded-md' />
        </CardHeader>
      </Card>

      <div className='grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_360px]'>
        <Card>
          <CardHeader>
            <Skeleton className='h-6 w-24' />
          </CardHeader>
          <CardContent className='grid gap-4 md:grid-cols-2'>
            {[0, 1, 2, 3].map((item) => (
              <Skeleton key={item} className='h-16 w-full rounded-2xl' />
            ))}
            <Skeleton className='h-28 w-full rounded-2xl md:col-span-2' />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <Skeleton className='h-6 w-24' />
          </CardHeader>
          <CardContent className='space-y-3'>
            {[0, 1, 2, 3].map((item) => (
              <Skeleton key={item} className='h-16 w-full rounded-2xl' />
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

type ProfileInfoItemProps = {
  label: string
  value: string
  icon: React.ComponentType<{ className?: string }>
  className?: string
}

function ProfileInfoItem({
  label,
  value,
  icon: Icon,
  className,
}: ProfileInfoItemProps) {
  return (
    <div className={className}>
      <div className='rounded-2xl border bg-background px-4 py-4'>
        <div className='mb-2 flex items-center gap-2 text-muted-foreground'>
          <Icon className='size-4' />
          <span className='text-sm'>{label}</span>
        </div>
        <p className='text-sm font-semibold tracking-tight break-all'>
          {value}
        </p>
      </div>
    </div>
  )
}

export function ProfileAccountForm() {
  const authUser = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const queryClient = useQueryClient()
  const [isEditing, setIsEditing] = useState(false)

  const profileQuery = useQuery({
    queryKey: ['auth', 'current-user'],
    queryFn: fetchCurrentUser,
    initialData: authUser ?? undefined,
  })

  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: {
      nickname: '',
      email: '',
      phone: '',
      sex: '0',
      remark: '',
    },
  })

  useEffect(() => {
    if (!profileQuery.data) {
      return
    }

    setUser(profileQuery.data)

    if (!isEditing) {
      form.reset(buildProfileFormValues(profileQuery.data))
    }
  }, [profileQuery.data, setUser, form, isEditing])

  const user = profileQuery.data

  if (profileQuery.isPending && !user) {
    return <ProfileSkeleton />
  }

  if (!user) {
    return (
      <Card className='border-dashed'>
        <CardHeader>
          <CardTitle>暂无个人资料</CardTitle>
        </CardHeader>
      </Card>
    )
  }

  const fallbackText = user.nickname?.slice(0, 1) || user.username.slice(0, 1)
  const archiveItems = [
    {
      label: '最近登录地点',
      value: formatText(user.loginLocation),
      icon: MapPin,
    },
    {
      label: '最近登录 IP',
      value: formatText(user.loginIp),
      icon: Network,
    },
    {
      label: '最近登录时间',
      value: formatDateTime(user.loginDate),
      icon: CalendarClock,
    },
    {
      label: '创建时间',
      value: formatDateTime(user.createTime),
      icon: CalendarClock,
    },
  ]
  const handleStartEdit = () => {
    form.reset(buildProfileFormValues(user))
    setIsEditing(true)
  }

  const handleCancelEdit = () => {
    form.reset(buildProfileFormValues(user))
    setIsEditing(false)
  }

  const refreshCurrentUser = () =>
    queryClient.fetchQuery({
      queryKey: ['auth', 'current-user'],
      queryFn: fetchCurrentUser,
    })

  const handleSave = async (values: ProfileFormValues) => {
    form.clearErrors()

    try {
      const editableUser =
        user.version == null ? await refreshCurrentUser() : user

      await updateProfile(buildProfileUpdatePayload(editableUser, values))
      await refreshCurrentUser()
      setIsEditing(false)
      toast.success('个人资料已更新。')
    } catch (error) {
      if (error instanceof AxiosError) {
        const responseData = error.response?.data as
          | ApiResult<unknown>
          | undefined
        const { fieldErrors, generalErrors } = extractProfileServerErrors(
          responseData?.message
        )

        let hasFieldError = false
        for (const [field, message] of Object.entries(fieldErrors)) {
          if (!message) {
            continue
          }

          form.setError(field as keyof ProfileFormValues, {
            type: 'server',
            message,
          })
          hasFieldError = true
        }

        if (generalErrors.length > 0) {
          toast.error(generalErrors[0])
          return
        }

        if (hasFieldError) {
          return
        }
      }

      toast.error('保存失败，请重试。')
    }
  }

  return (
    <div className='space-y-6'>
      <Card className='border-border/70 shadow-sm'>
        <CardHeader className='flex flex-wrap items-center justify-between gap-5 px-6 py-6'>
          <div className='flex min-w-0 items-center gap-6'>
            <Avatar className='h-24 w-24 shrink-0 border bg-muted'>
              <AvatarImage
                src={user.avatar}
                alt={user.nickname || user.username}
              />
              <AvatarFallback className='text-4xl font-semibold'>
                {fallbackText}
              </AvatarFallback>
            </Avatar>

            <div className='min-w-0 space-y-3'>
              <div className='flex flex-wrap items-center gap-3'>
                <CardTitle className='text-3xl font-semibold tracking-tight'>
                  {user.nickname || user.username}
                </CardTitle>
                <Badge className='bg-emerald-100 text-emerald-800 hover:bg-emerald-100 dark:bg-emerald-500/15 dark:text-emerald-300'>
                  {formatUserStatus(user.status)}
                </Badge>
              </div>

              <div className='space-y-2.5 text-base text-foreground/90'>
                <div className='flex items-center gap-2'>
                  <UserRound className='size-4 text-muted-foreground' />
                  <span>{user.username}</span>
                </div>
                <div className='flex items-center gap-2'>
                  <Building2 className='size-4 text-muted-foreground' />
                  <span>{formatText(user.deptName)}</span>
                </div>
              </div>
            </div>
          </div>

          <CardAction className='shrink-0'>
            <div className='flex gap-2'>
              {isEditing ? (
                <>
                  <Button variant='outline' onClick={handleCancelEdit}>
                    <X />
                    取消
                  </Button>
                  <Button type='submit' form='profile-form'>
                    <Save />
                    保存
                  </Button>
                </>
              ) : (
                <Button onClick={handleStartEdit}>
                  <PencilLine />
                  编辑资料
                </Button>
              )}
            </div>
          </CardAction>
        </CardHeader>
      </Card>

      <div className='grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_360px]'>
        <div className='space-y-4'>
          <h2 className='text-2xl font-semibold tracking-tight'>基础资料</h2>
          {isEditing ? (
            <Form {...form}>
              <form
                id='profile-form'
                onSubmit={form.handleSubmit(handleSave)}
                className='grid gap-x-6 gap-y-5 md:grid-cols-2'
              >
                <FormField
                  control={form.control}
                  name='email'
                  render={({ field }) => (
                    <FormItem className='gap-3'>
                      <FormLabel className='flex items-center gap-2 text-base font-semibold text-foreground'>
                        <Mail className='size-4.5 text-muted-foreground' />
                        邮箱
                      </FormLabel>
                      <FormControl>
                        <Input placeholder='请输入邮箱' {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='phone'
                  render={({ field }) => (
                    <FormItem className='gap-3'>
                      <FormLabel className='flex items-center gap-2 text-base font-semibold text-foreground'>
                        <Phone className='size-4.5 text-muted-foreground' />
                        手机号
                      </FormLabel>
                      <FormControl>
                        <Input placeholder='请输入手机号' {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='sex'
                  render={({ field }) => (
                    <FormItem className='gap-3'>
                      <FormLabel className='flex items-center gap-2 text-base font-semibold text-foreground'>
                        <VenusAndMars className='size-4.5 text-muted-foreground' />
                        性别
                      </FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger className='w-full'>
                            <SelectValue placeholder='请选择性别' />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value='0'>未知</SelectItem>
                          <SelectItem value='1'>男</SelectItem>
                          <SelectItem value='2'>女</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='nickname'
                  render={({ field }) => (
                    <FormItem className='gap-3'>
                      <FormLabel className='flex items-center gap-2 text-base font-semibold text-foreground'>
                        <UserRound className='size-4.5 text-muted-foreground' />
                        昵称
                      </FormLabel>
                      <FormControl>
                        <Input placeholder='请输入昵称' {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name='remark'
                  render={({ field }) => (
                    <FormItem className='gap-3 md:col-span-2'>
                      <FormLabel className='flex items-center gap-2 text-base font-semibold text-foreground'>
                        <UserCircle2 className='size-4.5 text-muted-foreground' />
                        备注
                      </FormLabel>
                      <FormControl>
                        <Textarea
                          {...field}
                          placeholder='请输入备注'
                          className='min-h-24 resize-none'
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </form>
            </Form>
          ) : (
            <div className='grid gap-4 md:grid-cols-2'>
              <ProfileInfoItem
                label='邮箱'
                value={formatText(user.email)}
                icon={Mail}
              />
              <ProfileInfoItem
                label='手机号'
                value={formatText(user.phone)}
                icon={Phone}
              />
              <ProfileInfoItem
                label='性别'
                value={formatUserSex(user.sex)}
                icon={VenusAndMars}
              />
              <ProfileInfoItem
                label='昵称'
                value={formatText(user.nickname)}
                icon={UserRound}
              />
              <ProfileInfoItem
                label='备注'
                value={formatText(user.remark)}
                icon={UserCircle2}
                className='md:col-span-2'
              />
            </div>
          )}
        </div>

        <div className='space-y-4'>
          <h2 className='text-2xl font-semibold tracking-tight'>账号记录</h2>
          <div className='space-y-4'>
            {archiveItems.map((item) => (
              <ProfileInfoItem
                key={item.label}
                label={item.label}
                value={item.value}
                icon={item.icon}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
