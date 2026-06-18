import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { type NavigateFn } from '@/hooks/use-table-url-state'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { fetchUsers } from './api'
import { UsersDialogs } from './components/users-dialogs'
import { UsersPrimaryButtons } from './components/users-primary-buttons'
import { UsersProvider } from './components/users-provider'
import { UsersTable } from './components/users-table'
import { userManagementSearchSchema } from './search-schema'

type UserManagementPageProps = {
  search: Record<string, unknown>
  navigate: NavigateFn
}

export function UserManagementPage({
  search,
  navigate,
}: UserManagementPageProps) {
  const parsedSearch = userManagementSearchSchema.parse(search)
  const usersQuery = useQuery({
    queryKey: ['system', 'users', 'list', parsedSearch],
    queryFn: () => fetchUsers(parsedSearch),
    placeholderData: keepPreviousData,
  })

  const userPage = usersQuery.data ?? {
    pageNum: parsedSearch.page,
    pageSize: parsedSearch.pageSize,
    total: 0,
    pages: 0,
    records: [],
  }

  return (
    <UsersProvider>
      <Header fixed>
        <div className='flex items-center space-x-4'>
          <Search />
          <ProfileDropdown />
        </div>
      </Header>

      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-wrap items-end justify-between gap-3'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>用户管理</h2>
          </div>
          <UsersPrimaryButtons />
        </div>
        <UsersTable
          data={userPage.records}
          total={userPage.total}
          pageCount={userPage.pages}
          isLoading={usersQuery.isFetching && !usersQuery.data}
          search={parsedSearch}
          navigate={navigate}
        />
      </Main>

      <UsersDialogs />
    </UsersProvider>
  )
}
