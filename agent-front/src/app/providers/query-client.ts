import { AxiosError } from 'axios'
import { QueryCache, QueryClient } from '@tanstack/react-query'
import type { AppRouter } from '@/app/router'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/auth-store'
import { handleServerError } from '@/lib/handle-server-error'

type GetRouter = () => AppRouter | null

export function createAppQueryClient(getRouter: GetRouter) {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => {
          // eslint-disable-next-line no-console
          if (import.meta.env.DEV) console.log({ failureCount, error })

          if (failureCount >= 0 && import.meta.env.DEV) return false
          if (failureCount > 3 && import.meta.env.PROD) return false

          return !(
            error instanceof AxiosError &&
            [401, 403].includes(error.response?.status ?? 0)
          )
        },
        refetchOnWindowFocus: import.meta.env.PROD,
        staleTime: 10 * 1000,
      },
      mutations: {
        onError: (error) => {
          handleServerError(error)

          if (error instanceof AxiosError) {
            if (error.response?.status === 304) {
              toast.error('Content not modified!')
            }
          }
        },
      },
    },
    queryCache: new QueryCache({
      onError: (error) => {
        if (!(error instanceof AxiosError)) {
          return
        }

        const router = getRouter()

        if (error.response?.status === 401) {
          toast.error('Session expired!')
          useAuthStore.getState().reset()

          if (router) {
            const redirect = `${router.history.location.href}`
            router.navigate({
              to: '/otp',
              search: { redirect },
            })
          }
        }

        if (error.response?.status === 500) {
          toast.error('Internal Server Error!')

          if (import.meta.env.PROD && router) {
            router.navigate({ to: '/500' })
          }
        }
      },
    }),
  })
}
