// 后端以标准 HTTP Status 作为成败依据；body.code 仅用于细分错误类型，不作为前端成功判断依据。
export interface ApiResult<T> {
  code: number
  message: string
  data: T
  traceId?: string
  timestamp: number
}
