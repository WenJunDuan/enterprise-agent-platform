import { isAxiosError } from 'axios'
import { REQUIRE_ADMIN_AUTH } from '@/config/app'
import type { AuthUser } from '@/types/auth'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/auth-store'
import {
  clearTenantToken,
  persistTenantToken,
  resolveTenantTokenByPin,
  validateTenantToken,
} from '@/features/audit/api'
import { fetchCurrentUser, logoutCurrentUser } from './api'

let bootstrapPromise: Promise<AuthUser | null> | null = null

const tenantAuthUser: AuthUser = {
  id: 'tenant-audit-operator',
  username: 'tenant-audit-operator',
  nickname: '审核操作员',
  email: 'tenant@agent-front',
  roles: ['admin'],
  permissions: ['*:*:*'],
}

export function ensureTenantSession(tenantToken: string) {
  const token = tenantToken.trim()
  if (!token) return null

  const authState = useAuthStore.getState()
  authState.setSession({ accessToken: token })
  authState.setUser(authState.user || tenantAuthUser)
  authState.setBootstrapStatus('ready')

  return useAuthStore.getState().user
}

export async function loginWithTenantToken(tenantToken: string) {
  const token = tenantToken.trim()
  const authState = useAuthStore.getState()

  authState.setBootstrapStatus('loading')

  try {
    await validateTenantToken(token)
    persistTenantToken(token)
    return ensureTenantSession(token)
  } catch (error) {
    authState.setBootstrapStatus('idle')
    throw error
  }
}

export async function loginWithTenantPin(pin: string) {
  const tenantToken = resolveTenantTokenByPin(pin)
  if (!tenantToken) {
    throw new Error('访问 PIN 无效')
  }

  return loginWithTenantToken(tenantToken)
}

export async function bootstrapAuthSession() {
  const authState = useAuthStore.getState()
  if (authState.accessToken && authState.user) {
    authState.setBootstrapStatus('ready')
    return authState.user
  }

  if (bootstrapPromise) {
    return bootstrapPromise
  }

  authState.setBootstrapStatus('loading')
  bootstrapPromise = fetchCurrentUser()
    .then((user) => {
      const currentState = useAuthStore.getState()
      currentState.setUser(user)
      currentState.setBootstrapStatus('ready')
      return user
    })
    .catch((error) => {
      const currentState = useAuthStore.getState()
      const status = isAxiosError(error) ? error.response?.status : undefined

      if (status === 401 || status === 403) {
        currentState.reset()
      } else {
        currentState.setBootstrapStatus('idle')
      }

      throw error
    })
    .finally(() => {
      bootstrapPromise = null
    })

  return bootstrapPromise
}

export async function logoutSession() {
  if (!REQUIRE_ADMIN_AUTH) {
    clearTenantToken()
    useAuthStore.getState().reset()
    return
  }

  try {
    await logoutCurrentUser()
  } catch {
    toast.error('服务端登出失败，请手动关闭浏览器或清除浏览器 Cookie 后重试')
  } finally {
    useAuthStore.getState().reset()
  }
}
