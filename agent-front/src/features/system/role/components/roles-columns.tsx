import { type ColumnDef } from '@tanstack/react-table'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { DataTableColumnHeader } from '@/components/data-table'
import { LongText } from '@/components/long-text'
import { getRoleStatusLabel, roleStatusTone } from '../data'
import {
  getRoleDataScopeLabel,
  getRoleDataScopeTone,
  type Role,
} from '../model'
import { isProtectedSystemRole } from '../role-management-access'
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

const rolesColumns: ColumnDef<Role>[] = [
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
        aria-label={
          row.getCanSelect() ? '选择当前行' : '系统内置角色不允许选中'
        }
        disabled={!row.getCanSelect()}
        title={
          isProtectedSystemRole(row.original.id)
            ? '系统内置角色不允许选中'
            : undefined
        }
        className='translate-y-[2px]'
      />
    ),
    enableSorting: false,
    enableHiding: false,
  },
  {
    accessorKey: 'roleName',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='角色名称' />
    ),
    cell: ({ row }) => (
      <LongText className='max-w-40 ps-3'>{row.original.roleName}</LongText>
    ),
    meta: {
      label: '角色名称',
      className: cn(
        'drop-shadow-[0_1px_2px_rgb(0_0_0_/_0.1)] dark:drop-shadow-[0_1px_2px_rgb(255_255_255_/_0.1)]',
        'ps-0.5 max-md:sticky start-6 @4xl/content:table-cell @4xl/content:drop-shadow-none'
      ),
    },
    enableHiding: false,
    enableSorting: false,
  },
  {
    accessorKey: 'roleKey',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='角色标识' />
    ),
    cell: ({ row }) => (
      <code className='rounded bg-muted px-2 py-0.5 text-xs'>
        {row.original.roleKey}
      </code>
    ),
    meta: {
      label: '角色标识',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'orderNum',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='显示顺序' />
    ),
    cell: ({ row }) => (
      <div className='text-center tabular-nums'>{row.original.orderNum}</div>
    ),
    meta: {
      label: '显示顺序',
      className: 'w-24',
    },
    enableSorting: false,
  },
  {
    accessorKey: 'dataScope',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='数据权限' />
    ),
    cell: ({ row }) => (
      <Badge
        variant='outline'
        className={cn(getRoleDataScopeTone(row.original.dataScope))}
      >
        {getRoleDataScopeLabel(row.original.dataScope)}
      </Badge>
    ),
    meta: {
      label: '数据权限',
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
        <Badge
          variant='outline'
          className={cn('capitalize', roleStatusTone.get(status))}
        >
          {getRoleStatusLabel(status)}
        </Badge>
      )
    },
    meta: {
      label: '状态',
    },
    enableHiding: false,
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

type RolesColumnsOptions = {
  enableBulkActions: boolean
  enableRowActions: boolean
}

export function getRolesColumns({
  enableBulkActions,
  enableRowActions,
}: RolesColumnsOptions) {
  return rolesColumns.filter((column) => {
    if (column.id === 'select') {
      return enableBulkActions
    }

    if (column.id === 'actions') {
      return enableRowActions
    }

    return true
  })
}
