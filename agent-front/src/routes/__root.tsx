import { type QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, Outlet } from '@tanstack/react-router'
import { AppDevtools } from '@/components/app-devtools'
import { Toaster } from '@/components/ui/sonner'
import { SearchProvider } from '@/context/search-provider'
import { GeneralError } from '@/features/errors/general-error'
import { NotFoundError } from '@/features/errors/not-found-error'

export const Route = createRootRouteWithContext<{
  queryClient: QueryClient
}>()({
  component: () => {
    return (
      <SearchProvider>
        <Outlet />
        <Toaster duration={5000} />
        <AppDevtools />
      </SearchProvider>
    )
  },
  notFoundComponent: NotFoundError,
  errorComponent: GeneralError,
})
