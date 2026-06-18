import { useEffect, useState } from 'react'
import {
  type VisibilityState,
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getFacetedRowModel,
  getFacetedUniqueValues,
  useReactTable,
} from '@tanstack/react-table'
import { useAuthStore } from '@/stores/auth-store'
import { cn } from '@/lib/utils'
import { type NavigateFn, useTableUrlState } from '@/hooks/use-table-url-state'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { DataTablePagination, DataTableToolbar } from '@/components/data-table'
import { userSexOptions, userStatuses } from '../data/data'
import { type User } from '../data/schema'
import { type UserManagementSearchState } from '../search-schema'
import { canSelectSystemUser } from '../user-guards'
import { getUserManagementAccess } from '../user-management-access'
import { DataTableBulkActions } from './data-table-bulk-actions'
import { getUsersColumns } from './users-columns'

type DataTableProps = {
  data: User[]
  search: UserManagementSearchState
  navigate: NavigateFn
  pageCount: number
  total: number
  isLoading: boolean
}

export function UsersTable({
  data,
  search,
  navigate,
  pageCount,
  total,
  isLoading,
}: DataTableProps) {
  const authUser = useAuthStore((state) => state.user)
  const { canBulkDeleteUsers, hasRowActions } =
    getUserManagementAccess(authUser)
  const columns = getUsersColumns({
    enableBulkActions: canBulkDeleteUsers,
    enableRowActions: hasRowActions,
  }) as ColumnDef<User>[]

  const [rowSelection, setRowSelection] = useState({})
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({})

  const {
    columnFilters,
    onColumnFiltersChange,
    pagination,
    onPaginationChange,
    ensurePageInRange,
  } = useTableUrlState({
    search,
    navigate,
    pagination: { defaultPage: 1, defaultPageSize: 10 },
    globalFilter: { enabled: false },
    columnFilters: [
      { columnId: 'username', searchKey: 'username', type: 'string' },
      { columnId: 'nickname', searchKey: 'nickname', type: 'string' },
      { columnId: 'email', searchKey: 'email', type: 'string' },
      { columnId: 'phone', searchKey: 'phone', type: 'string' },
      { columnId: 'sex', searchKey: 'sex', type: 'array' },
      { columnId: 'status', searchKey: 'status', type: 'array' },
    ],
  })

  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns,
    state: {
      pagination,
      rowSelection,
      columnFilters,
      columnVisibility,
    },
    manualPagination: true,
    manualFiltering: true,
    pageCount: Math.max(pageCount, 1),
    rowCount: total,
    enableRowSelection: (row) =>
      canBulkDeleteUsers && canSelectSystemUser(row.original),
    onPaginationChange,
    onColumnFiltersChange,
    onRowSelectionChange: setRowSelection,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getFacetedRowModel: getFacetedRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
  })

  useEffect(() => {
    ensurePageInRange(Math.max(pageCount, 1))
  }, [pageCount, ensurePageInRange])

  return (
    <div
      className={cn(
        'max-sm:has-[div[role="toolbar"]]:mb-16',
        'flex flex-1 flex-col gap-4'
      )}
    >
      <DataTableToolbar
        table={table}
        searches={[
          {
            columnId: 'username',
            placeholder: '按用户名检索...',
          },
          {
            columnId: 'nickname',
            placeholder: '按昵称检索...',
          },
          {
            columnId: 'email',
            placeholder: '按邮箱检索...',
          },
          {
            columnId: 'phone',
            placeholder: '按手机号检索...',
          },
        ]}
        filters={[
          {
            columnId: 'sex',
            title: '性别',
            options: userSexOptions.map(({ label, value, icon }) => ({
              label,
              value,
              icon,
            })),
          },
          {
            columnId: 'status',
            title: '状态',
            options: userStatuses.map((status) => ({ ...status })),
          },
        ]}
      />
      <div className='overflow-hidden rounded-md border'>
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className='group/row'>
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    colSpan={header.colSpan}
                    className={cn(
                      'bg-background group-hover/row:bg-muted group-data-[state=selected]/row:bg-muted',
                      header.column.columnDef.meta?.className,
                      header.column.columnDef.meta?.thClassName
                    )}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className='h-24 text-center text-muted-foreground'
                >
                  用户数据加载中...
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && 'selected'}
                  className='group/row'
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        'bg-background group-hover/row:bg-muted group-data-[state=selected]/row:bg-muted',
                        cell.column.columnDef.meta?.className,
                        cell.column.columnDef.meta?.tdClassName
                      )}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className='h-24 text-center'
                >
                  暂无结果。
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <DataTablePagination table={table} className='mt-auto' />
      {canBulkDeleteUsers && <DataTableBulkActions table={table} />}
    </div>
  )
}
