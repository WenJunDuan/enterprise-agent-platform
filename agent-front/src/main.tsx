import { StrictMode } from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { AppProviders, createAppQueryClient } from '@/app/providers'
import { createAppRouter } from '@/app/router'
import { APP_TITLE } from '@/config/app'
import './styles/index.css'

let router: ReturnType<typeof createAppRouter> | null = null
const queryClient = createAppQueryClient(() => router)
router = createAppRouter(queryClient)

const rootElement = document.getElementById('root')!
if (!rootElement.innerHTML) {
  document.title = APP_TITLE
  const root = ReactDOM.createRoot(rootElement)
  root.render(
    <StrictMode>
      <AppProviders queryClient={queryClient}>
        <RouterProvider router={router} />
      </AppProviders>
    </StrictMode>
  )
}
