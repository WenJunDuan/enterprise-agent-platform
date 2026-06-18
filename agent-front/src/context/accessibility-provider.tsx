import { createContext, useContext, useEffect, useState } from 'react'
import { getCookie, removeCookie, setCookie } from '@/lib/cookies'

const ELDER_MODE_COOKIE_NAME = 'elder_mode'
const ELDER_MODE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 // 1 year

type AccessibilityContextType = {
  elderMode: boolean
  setElderMode: (enabled: boolean) => void
  resetAccessibility: () => void
}

const AccessibilityContext = createContext<AccessibilityContextType | null>(null)

export function AccessibilityProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [elderMode, _setElderMode] = useState<boolean>(() => {
    return getCookie(ELDER_MODE_COOKIE_NAME) === 'true'
  })

  useEffect(() => {
    const root = document.documentElement
    root.dataset.elderMode = String(elderMode)

    if (elderMode) {
      root.classList.add('elder')
    } else {
      root.classList.remove('elder')
    }
  }, [elderMode])

  const setElderMode = (enabled: boolean) => {
    setCookie(ELDER_MODE_COOKIE_NAME, String(enabled), ELDER_MODE_COOKIE_MAX_AGE)
    _setElderMode(enabled)
  }

  const resetAccessibility = () => {
    removeCookie(ELDER_MODE_COOKIE_NAME)
    _setElderMode(false)
  }

  return (
    <AccessibilityContext
      value={{ elderMode, setElderMode, resetAccessibility }}
    >
      {children}
    </AccessibilityContext>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAccessibility() {
  const context = useContext(AccessibilityContext)

  if (!context) {
    throw new Error(
      'useAccessibility must be used within an AccessibilityProvider'
    )
  }

  return context
}
