import { createFileRoute, redirect } from '@tanstack/react-router'
import { ensureRouteAccess } from '@/app/auth/access'
import { navigationQueryOptions } from '@/app/navigation/api'
import { findBackendRouteByPath } from '@/app/navigation/registry'
import { getBackendPageByPath } from '@/app/navigation/page-registry'
import { dynamicPageSearchSchema } from '@/app/navigation/search-schema'

export const Route = createFileRoute('/_authenticated/$section/$page')({
  validateSearch: dynamicPageSearchSchema,
  beforeLoad: async ({ context, location }) => {
    const pathname = location.pathname.replace(/\/+$/, '') || '/'
    const pageDefinition = getBackendPageByPath(pathname)

    if (!pageDefinition) {
      throw redirect({ to: '/404' })
    }

    const routers = await context.queryClient.ensureQueryData(
      navigationQueryOptions()
    )

    const backendRoute = findBackendRouteByPath(routers, pathname)
    if (!backendRoute) {
      throw redirect({
        to: '/403',
        search: { redirect: location.href },
      })
    }

    if (backendRoute.router.component !== pageDefinition.backendComponent) {
      throw redirect({ to: '/404' })
    }

    ensureRouteAccess({
      locationHref: location.href,
      permissions: backendRoute.router.meta?.permission
        ? [backendRoute.router.meta.permission]
        : [],
      roles: backendRoute.router.meta?.roles ?? [],
    })
  },
  component: RouteComponent,
})

// eslint-disable-next-line react-refresh/only-export-components
function RouteComponent() {
  const search = Route.useSearch()
  const navigate = Route.useNavigate()
  const { section, page } = Route.useParams()
  const pathname = `/${section}/${page}`.replace(/\/+$/, '') || '/'
  const pageDefinition = getBackendPageByPath(pathname)

  if (!pageDefinition) {
    return null
  }

  return pageDefinition.render({
    navigate,
    search,
  })
}
