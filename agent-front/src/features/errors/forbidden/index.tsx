import { useEffect } from 'react'
import { useNavigate, useRouter } from '@tanstack/react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'

type ForbiddenErrorProps = {
  autoRedirectToAuth?: boolean
  message?: string
  redirect?: string
}

export function ForbiddenError({
  autoRedirectToAuth = false,
  message,
  redirect,
}: ForbiddenErrorProps = {}) {
  const navigate = useNavigate()
  const { history } = useRouter()

  useEffect(() => {
    if (!autoRedirectToAuth) {
      return
    }

    toast.error(message || '当前访问凭据不可用')

    const timeoutId = window.setTimeout(() => {
      navigate({
        to: '/otp',
        search: redirect ? { redirect } : undefined,
        replace: true,
      })
    }, 1500)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [autoRedirectToAuth, message, navigate, redirect])

  return (
    <div className='h-svh'>
      <div className='m-auto flex h-full w-full flex-col items-center justify-center gap-2'>
        <h1 className='text-[7rem] leading-tight font-bold'>403</h1>
        <span className='font-medium'>
          {autoRedirectToAuth ? '访问未授权' : '无权限访问'}
        </span>
        <p className='text-center text-muted-foreground'>
          {autoRedirectToAuth ? (
            <>
              {message || '当前访问凭据不可用'}
              <br />
              正在返回授权页，请联系管理员处理。
            </>
          ) : (
            <>
              您当前没有访问此资源的必要权限。
              <br />
              请联系管理员处理。
            </>
          )}
        </p>
        <div className='mt-6 flex gap-4'>
          <Button variant='outline' onClick={() => history.go(-1)}>
            返回上一页
          </Button>
          <Button
            onClick={() =>
              autoRedirectToAuth
                ? navigate({
                    to: '/otp',
                    search: redirect ? { redirect } : undefined,
                    replace: true,
                  })
                : navigate({ to: '/' })
            }
          >
            {autoRedirectToAuth ? '前往授权页' : '返回首页'}
          </Button>
        </div>
      </div>
    </div>
  )
}
