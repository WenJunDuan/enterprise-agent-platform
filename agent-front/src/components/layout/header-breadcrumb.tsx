import { Link, useLocation } from '@tanstack/react-router'
import { House } from 'lucide-react'
import { getBreadcrumbsForPath } from '@/app/navigation/registry'
import { useNavigation } from '@/app/navigation/use-navigation'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'

type Crumb = {
  label: string
  href?: string
}

const errorLabelMap: Record<string, string> = {
  unauthorized: '未授权',
  forbidden: '无权限',
  'not-found': '页面不存在',
  'internal-server-error': '服务器错误',
  'maintenance-error': '维护中',
}

function getBreadcrumbs(
  pathname: string,
  menuRouters?: Parameters<typeof getBreadcrumbsForPath>[1]
): Crumb[] {
  const cleanPath = pathname.replace(/\/+$/, '') || '/'

  if (cleanPath.startsWith('/errors/')) {
    const errorKey = cleanPath.replace('/errors/', '')
    return [{ label: '错误页' }, { label: errorLabelMap[errorKey] ?? '异常' }]
  }

  return getBreadcrumbsForPath(cleanPath, menuRouters)
}

export function HeaderBreadcrumb() {
  const pathname = useLocation({ select: (location) => location.pathname })
  const { menuRouters } = useNavigation()
  const crumbs = getBreadcrumbs(pathname, menuRouters)

  return (
    <Breadcrumb className='min-w-0 flex-1'>
      <BreadcrumbList className='flex-nowrap overflow-hidden whitespace-nowrap'>
        <BreadcrumbItem className='shrink-0'>
          <BreadcrumbLink asChild>
            <Link
              to='/'
              aria-label='返回首页'
              className='inline-flex size-8 items-center justify-center rounded-full border bg-background text-foreground shadow-xs transition-colors hover:bg-accent'
            >
              <House aria-hidden='true' className='size-4.5 stroke-[2.2]' />
            </Link>
          </BreadcrumbLink>
        </BreadcrumbItem>
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1

          return (
            <BreadcrumbItem key={`${crumb.label}-${index}`} className='min-w-0'>
              <BreadcrumbSeparator />
              {isLast || !crumb.href ? (
                <BreadcrumbPage className='truncate'>
                  {crumb.label}
                </BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild className='truncate'>
                  <Link to={crumb.href}>{crumb.label}</Link>
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
