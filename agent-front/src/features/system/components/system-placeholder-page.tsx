import {
  Blocks,
  Database,
  Building2,
  type LucideIcon,
  Server,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const placeholderIconMap: Record<string, LucideIcon> = {
  role: ShieldCheck,
  menu: Blocks,
  dept: Building2,
  cache: Database,
  online: Users,
  server: Server,
}

type SystemPlaceholderPageProps = {
  title: string
  description: string
  backendComponent: string
  routePath: string
  iconKey: keyof typeof placeholderIconMap
}

export function SystemPlaceholderPage({
  title,
  description,
  backendComponent,
  routePath,
  iconKey,
}: SystemPlaceholderPageProps) {
  const Icon = placeholderIconMap[iconKey]

  return (
    <>
      <Header fixed>
        <div className='flex items-center space-x-4'>
          <Search />
          <ProfileDropdown />
        </div>
      </Header>

      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-wrap items-end justify-between gap-3'>
          <div className='space-y-1'>
            <h2 className='text-2xl font-bold tracking-tight'>{title}</h2>
            <p className='text-muted-foreground'>{description}</p>
          </div>
        </div>

        <Card className='border-dashed'>
          <CardHeader className='flex flex-row items-start gap-4 space-y-0'>
            <div className='rounded-xl border bg-muted/40 p-3'>
              <Icon className='size-5 text-muted-foreground' />
            </div>
            <div className='space-y-1'>
              <CardTitle>占位页面已创建</CardTitle>
              <p className='text-sm text-muted-foreground'>
                当前页面已接入动态菜单与动态路由，后续可以直接在此补真实列表、表单和交互逻辑。
              </p>
            </div>
          </CardHeader>
          <CardContent className='space-y-4 text-sm'>
            <div className='rounded-lg border bg-muted/30 p-4'>
              <p className='font-medium'>当前映射</p>
              <p className='mt-2 text-muted-foreground'>
                路由地址：<span className='font-mono text-foreground'>{routePath}</span>
              </p>
              <p className='mt-1 text-muted-foreground'>
                后端组件：<span className='font-mono text-foreground'>{backendComponent}</span>
              </p>
            </div>
            <div className='rounded-lg border bg-background p-4'>
              <p className='font-medium'>下一步建议</p>
              <p className='mt-2 text-muted-foreground'>
                1. 接对应接口与权限码
              </p>
              <p className='text-muted-foreground'>2. 落列表页与查询条件</p>
              <p className='text-muted-foreground'>3. 补新增、编辑、删除等操作弹层</p>
            </div>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
