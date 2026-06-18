import { Outlet } from '@tanstack/react-router'
import { Separator } from '@/components/ui/separator'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'

const settingsPageMeta = {
  profile: {
    title: '个人资料',
    description: '',
  },
} as const

export function Settings() {
  const pageMeta = settingsPageMeta.profile

  return (
    <>
      {/* ===== Top Heading ===== */}
      <Header>
        <div className='flex items-center space-x-4'>
          <Search />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='space-y-0.5'>
          <h1 className='text-2xl font-bold tracking-tight md:text-3xl'>
            {pageMeta.title}
          </h1>
          {pageMeta.description ? (
            <p className='max-w-3xl text-muted-foreground'>
              {pageMeta.description}
            </p>
          ) : null}
        </div>
        <Separator className='my-4 lg:my-6' />
        <div className='pe-2 pb-10'>
          <Outlet />
        </div>
      </Main>
    </>
  )
}
