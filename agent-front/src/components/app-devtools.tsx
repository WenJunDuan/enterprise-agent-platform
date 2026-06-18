import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'
import { NavigationProgress } from '@/components/navigation-progress'

function isDevtoolsEnabled() {
  const value = import.meta.env.VITE_ENABLE_DEVTOOLS
  return import.meta.env.DEV && /^(1|true)$/i.test(value ?? '')
}

export function AppDevtools() {
  if (!isDevtoolsEnabled()) return null

  return (
    <>
      <NavigationProgress />
      <ReactQueryDevtools buttonPosition='bottom-left' />
      <TanStackRouterDevtools position='bottom-right' />
    </>
  )
}
