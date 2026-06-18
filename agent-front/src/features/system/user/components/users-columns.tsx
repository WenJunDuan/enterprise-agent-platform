import { type ColumnDef } from '@tanstack/react-table'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { DataTableColumnHeader } from '@/components/data-table'
import { LongText } from '@/components/long-text'
import {
  getUserSexLabel,
  getUserStatusLabel,
  userStatusTone,
} from '../data/data'
import { type User } from '../data/schema'
import { isProtectedSystemUser } from '../user-guards'
import { DataTableRowActions } from './data-table-row-actions'

function formatDateTimeCell(value: string | null) {
  if (!value) {
    return '未记录'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

const usersColumns: ColumnDef<User>[] = [
  {
    id: 'select',
    header: ({ table }) => (
      <Checkbox
        checked={
          table.getIsAllPageRowsSelected() ||
          (table.getIsSomePageRowsSelected() && 'indeterminate')
        }
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
        aria-label='全选'
        disabled={
          !table
            .getPaginationRowModel()
            .flatRows.some((row) => row.getCanSelect())
        }
        className='translate-y-[2px]'
      />
    ),
    meta: {
      className: cn('max-md:sticky start-0 z-10 rounded-tl-[inherit]'),
    },
    cell: ({ row }) => (
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label={row.getCanSelect() ? '选择当前行' : 'admin 用户不允许选中'}
        disabled={!row.getCanSelect()}
        title={
          isProtectedSystemUser(row.original)
            ? 'admin 用户不允许选中'
            : undefined
        }
        className='translate-y-[2px]'
      />
    ),
    enableSorting: false,
    enableHiding: false,
  },
  {
    accessorKey: 'username',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='用户名' />
    ),
    cell: ({ row }) => (
      <LongText className='max-w-40 ps-3'>{row.getValue('username')}</LongText>
    ),
    meta: {
      label: '用户名',
      className: cn(
        'drop-shadow-[0_1px_2px_rgb(0_0_0_/_0.1)] dark:drop-shadow-[0_1px_2px_rgb(255_255_255_/_0.1)]',
        'ps-0.5 max-md:sticky start-6 @4xl/content:table-cell @4xl/content:drop-shadow-none'
      ),
    },
    enableHiding: false,
    enableSorting: false,
  },
  {
    accessorKey: 'nickname',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='昵称' />
    ),
    cell: ({ row }) => (
      <LongText className='max-w-32'>{row.getValue('nickname')}</LongText>
    ),
    meta: {
      label: '昵称',
      className: 'w-32',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'deptName',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='部门名称' />
    ),
    cell: ({ row }) => (
      <LongText className='max-w-36'>
        {row.original.deptName || '未分配'}
      </LongText>
    ),
    meta: {
      label: '部门名称',
      className: 'w-36',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'email',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='邮箱' />
    ),
    cell: ({ row }) => (
      <div className='w-fit ps-2 text-nowrap'>
        {row.original.email || '未设置'}
      </div>
    ),
    meta: {
      label: '邮箱',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'phone',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='手机号' />
    ),
    cell: ({ row }) => <div>{row.original.phone || '未设置'}</div>,
    meta: {
      label: '手机号',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'sex',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='性别' />
    ),
    cell: ({ row }) => <div>{getUserSexLabel(row.original.sex)}</div>,
    meta: {
      label: '性别',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'status',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='状态' />
    ),
    cell: ({ row }) => {
      const { status } = row.original
      return (
        <div className='flex space-x-2'>
          <Badge
            variant='outline'
            className={cn('capitalize', userStatusTone.get(status))}
          >
            {getUserStatusLabel(status)}
          </Badge>
        </div>
      )
    },
    meta: {
      label: '状态',
    },
    enableHiding: false,
    enableSorting: false,
  },
  {
    accessorKey: 'loginDate',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='最近登录' />
    ),
    cell: ({ row }) => (
      <div className='min-w-40 text-sm'>
        {formatDateTimeCell(row.original.loginDate)}
      </div>
    ),
    meta: {
      label: '最近登录',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'createTime',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='创建时间' />
    ),
    cell: ({ row }) => (
      <div className='min-w-40 text-sm'>
        {formatDateTimeCell(row.original.createTime)}
      </div>
    ),
    meta: {
      label: '创建时间',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'remark',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='备注' />
    ),
    cell: ({ row }) => (
      <LongText className='max-w-48'>
        {row.original.remark || '未填写'}
      </LongText>
    ),
    meta: {
      label: '备注',
    },
    enableSorting: false,
  },
  {
    id: 'actions',
    cell: DataTableRowActions,
  },
]

type UsersColumnsOptions = {
  enableBulkActions: boolean
  enableRowActions: boolean
}

export function getUsersColumns({
  enableBulkActions,
  enableRowActions,
}: UsersColumnsOptions) {
  return usersColumns.filter((column) => {
    if (column.id === 'select') {
      return enableBulkActions
    }

    if (column.id === 'actions') {
      return enableRowActions
    }

    return true
  })
}
