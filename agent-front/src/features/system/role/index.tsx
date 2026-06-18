import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { type NavigateFn } from '@/hooks/use-table-url-state'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { fetchRoles } from './api'
import { RolesDialogs } from './components/roles-dialogs'
import { RolesPrimaryButtons } from './components/roles-primary-buttons'
import { RolesProvider } from './components/roles-provider'
import { RolesTable } from './components/roles-table'
import { roleManagementSearchSchema } from './search-schema'

type RoleManagementPageProps = {
  search: Record<string, unknown>
  navigate: NavigateFn
}

export function RoleManagementPage({
  search,
  navigate,
}: RoleManagementPageProps) {
  const parsedSearch = roleManagementSearchSchema.parse(search)
  const rolesQuery = useQuery({
    queryKey: ['system', 'role', 'list', parsedSearch],
    queryFn: () => fetchRoles(parsedSearch),
    placeholderData: keepPreviousData,
  })

  const rolePage = rolesQuery.data ?? {
    pageNum: parsedSearch.page,
    pageSize: parsedSearch.pageSize,
    total: 0,
    pages: 0,
    records: [],
  }

  return (
    <RolesProvider>
      <Header fixed>
        <div className='flex items-center space-x-4'>
          <Search />
          <ProfileDropdown />
        </div>
      </Header>

      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-wrap items-end justify-between gap-3'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>角色管理</h2>
          </div>
          <RolesPrimaryButtons />
        </div>
        <RolesTable
          data={rolePage.records}
          total={rolePage.total}
          pageCount={rolePage.pages}
          isLoading={rolesQuery.isFetching && !rolesQuery.data}
          search={parsedSearch}
          navigate={navigate}
        />
      </Main>

      <RolesDialogs />
    </RolesProvider>
  )
}
