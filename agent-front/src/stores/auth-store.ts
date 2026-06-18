import { create } from 'zustand'
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware'
import type { AuthUser, BootstrapStatus } from '@/types/auth'

const AUTH_STORAGE_KEY = 'talent_manager_auth'

type SessionTokens = {
  accessToken: string
  deviceId?: string
}

type TokenUpdate = {
  accessToken?: string
}

type PersistedAuthState = {
  deviceId: string
  user: AuthUser | null
}

type AuthState = PersistedAuthState & {
  accessToken: string
  bootstrapStatus: BootstrapStatus
  setSession: (tokens: SessionTokens) => void
  updateTokens: (tokens: TokenUpdate) => void
  setUser: (user: AuthUser | null) => void
  clearUser: () => void
  setBootstrapStatus: (status: BootstrapStatus) => void
  ensureDeviceId: () => string
  reset: () => void
}

const initialState: PersistedAuthState = {
  deviceId: '',
  user: null,
}

const browserStorage: StateStorage = {
  getItem: (name) =>
    typeof window !== 'undefined' ? window.localStorage.getItem(name) : null,
  setItem: (name, value) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(name, value)
    }
  },
  removeItem: (name) => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(name)
    }
  },
}

function createDeviceId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `device-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function stripBearerPrefix(token: string) {
  return token.startsWith('Bearer ') ? token.slice('Bearer '.length) : token
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      ...initialState,
      accessToken: '',
      bootstrapStatus: 'idle',
      setSession: ({ accessToken, deviceId }) =>
        set((state) => ({
          accessToken: stripBearerPrefix(accessToken),
          deviceId: deviceId || state.deviceId || createDeviceId(),
          bootstrapStatus: state.user ? 'ready' : state.bootstrapStatus,
        })),
      updateTokens: ({ accessToken }) =>
        set((state) => ({
          accessToken: accessToken
            ? stripBearerPrefix(accessToken)
            : state.accessToken,
        })),
      setUser: (user) =>
        set({
          user,
          bootstrapStatus: user ? 'ready' : 'idle',
        }),
      clearUser: () =>
        set({
          user: null,
          bootstrapStatus: 'idle',
        }),
      setBootstrapStatus: (bootstrapStatus) => set({ bootstrapStatus }),
      ensureDeviceId: () => {
        const existingDeviceId = get().deviceId
        if (existingDeviceId) {
          return existingDeviceId
        }

        const nextDeviceId = createDeviceId()
        set({ deviceId: nextDeviceId })
        return nextDeviceId
      },
      reset: () => {
        const deviceId = get().deviceId || createDeviceId()
        set({
          ...initialState,
          accessToken: '',
          bootstrapStatus: 'idle',
          deviceId,
        })
      },
    }),
    {
      name: AUTH_STORAGE_KEY,
      storage: createJSONStorage(() => browserStorage),
      partialize: (state) => ({
        deviceId: state.deviceId,
        user: state.user,
      }),
    }
  )
)
