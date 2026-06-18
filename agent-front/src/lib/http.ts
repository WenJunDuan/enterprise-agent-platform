import axios, {
  AxiosHeaders,
  type AxiosError,
  type AxiosResponseHeaders,
  type InternalAxiosRequestConfig,
  type RawAxiosResponseHeaders,
} from 'axios'
import { useAuthStore } from '@/stores/auth-store'

const REQUEST_TIMEOUT = 15000
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim() || '/api'
const HEADER_AUTHORIZATION = 'Authorization'
const HEADER_DEVICE_ID = 'X-Device-Id'
const BEARER_PREFIX = 'Bearer '
const PIN_SIGN_IN_PATH = '/otp'

function stripBearerPrefix(token?: string | null) {
  if (!token) {
    return ''
  }

  return token.startsWith(BEARER_PREFIX)
    ? token.slice(BEARER_PREFIX.length)
    : token
}

function setHeader(
  config: InternalAxiosRequestConfig,
  key: string,
  value: string
) {
  if (config.headers instanceof AxiosHeaders) {
    config.headers.set(key, value)
    return
  }

  const headers = AxiosHeaders.from(config.headers)
  headers.set(key, value)
  config.headers = headers
}

function getHeader(
  headers: AxiosResponseHeaders | RawAxiosResponseHeaders | undefined,
  key: string
) {
  if (!headers) {
    return undefined
  }

  const normalizedKey = key.toLowerCase()
  const value = headers[normalizedKey] ?? headers[key]

  if (Array.isArray(value)) {
    return value[0]
  }

  return typeof value === 'string' ? value : undefined
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: REQUEST_TIMEOUT,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const authState = useAuthStore.getState()
  const deviceId = authState.ensureDeviceId()

  setHeader(config, HEADER_DEVICE_ID, deviceId)

  if (authState.accessToken) {
    setHeader(
      config,
      HEADER_AUTHORIZATION,
      `${BEARER_PREFIX}${stripBearerPrefix(authState.accessToken)}`
    )
  }

  return config
})

apiClient.interceptors.response.use(
  (response) => {
    const accessToken = stripBearerPrefix(
      getHeader(response.headers, HEADER_AUTHORIZATION)
    )

    if (accessToken) {
      useAuthStore.getState().updateTokens({
        accessToken: accessToken || undefined,
      })
    }

    return response
  },
  (error: AxiosError) => {
    const status = error.response?.status

    if (status === 401) {
      useAuthStore.getState().reset()

      if (
        typeof window !== 'undefined' &&
        window.location.pathname !== PIN_SIGN_IN_PATH
      ) {
        const currentHref = `${window.location.pathname}${window.location.search}${window.location.hash}`
        const redirectParam = encodeURIComponent(currentHref)
        window.location.replace(`${PIN_SIGN_IN_PATH}?redirect=${redirectParam}`)
      }
    }

    return Promise.reject(error)
  }
)
