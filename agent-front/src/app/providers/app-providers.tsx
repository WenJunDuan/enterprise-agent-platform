import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { AccessibilityProvider } from '@/context/accessibility-provider'
import { DirectionProvider } from '@/context/direction-provider'
import { FontProvider } from '@/context/font-provider'
import { ThemeProvider } from '@/context/theme-provider'

type AppProvidersProps = {
  children: React.ReactNode
  queryClient: QueryClient
}

export function AppProviders({
  children,
  queryClient,
}: AppProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <AccessibilityProvider>
        <ThemeProvider>
          <FontProvider>
            <DirectionProvider>{children}</DirectionProvider>
          </FontProvider>
        </ThemeProvider>
      </AccessibilityProvider>
    </QueryClientProvider>
  )
}
