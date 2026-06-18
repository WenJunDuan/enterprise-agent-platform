import { AxiosError } from 'axios'
import type { ApiResult } from '@/types/api'
import { toast } from 'sonner'

type ErrorPayload = ApiResult<unknown> & {
  title?: string
}

export function handleServerError(error: unknown) {
  // eslint-disable-next-line no-console
  console.log(error)

  let errMsg = '操作未完成，请稍后重试。'

  if (
    error &&
    typeof error === 'object' &&
    'status' in error &&
    Number(error.status) === 204
  ) {
    errMsg = '请求没有返回内容。'
  }

  if (error instanceof AxiosError) {
    const responseData = error.response?.data as ErrorPayload | undefined
    errMsg = responseData?.message || responseData?.title || error.message
  } else if (error instanceof Error) {
    errMsg = error.message
  }

  toast.error(errMsg)
}
