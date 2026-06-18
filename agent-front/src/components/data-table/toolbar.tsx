import { Cross2Icon } from '@radix-ui/react-icons'
import { type Table } from '@tanstack/react-table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataTableFacetedFilter } from './faceted-filter'
import { DataTableViewOptions } from './view-options'

type DataTableToolbarProps<TData> = {
  table: Table<TData>
  searchPlaceholder?: string
  searchKey?: string
  searches?: {
    columnId: string
    placeholder?: string
    className?: string
  }[]
  filters?: {
    columnId: string
    title: string
    options: {
      label: string
      value: string
      icon?: React.ComponentType<{ className?: string }>
    }[]
  }[]
}

export function DataTableToolbar<TData>({
  table,
  searchPlaceholder = '筛选...',
  searchKey,
  searches = [],
  filters = [],
}: DataTableToolbarProps<TData>) {
  const isFiltered =
    table.getState().columnFilters.length > 0 || table.getState().globalFilter
  const searchFields =
    searches.length > 0
      ? searches
      : searchKey
        ? [{ columnId: searchKey, placeholder: searchPlaceholder }]
        : []

  return (
    <div className='flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between'>
      <div className='flex flex-1 flex-wrap items-center gap-2'>
        {searchFields.length > 0 ? (
          searchFields.map((searchField) => (
            <Input
              key={searchField.columnId}
              placeholder={searchField.placeholder ?? searchPlaceholder}
              value={
                (table
                  .getColumn(searchField.columnId)
                  ?.getFilterValue() as string) ?? ''
              }
              onChange={(event) =>
                table
                  .getColumn(searchField.columnId)
                  ?.setFilterValue(event.target.value)
              }
              className={searchField.className ?? 'h-8 w-[150px] lg:w-[200px]'}
            />
          ))
        ) : (
          <Input
            placeholder={searchPlaceholder}
            value={table.getState().globalFilter ?? ''}
            onChange={(event) => table.setGlobalFilter(event.target.value)}
            className='h-8 w-[150px] lg:w-[250px]'
          />
        )}
        <div className='flex flex-wrap items-center gap-2'>
          {filters.map((filter) => {
            const column = table.getColumn(filter.columnId)
            if (!column) return null
            return (
              <DataTableFacetedFilter
                key={filter.columnId}
                column={column}
                title={filter.title}
                options={filter.options}
              />
            )
          })}
        </div>
        {isFiltered && (
          <Button
            variant='ghost'
            onClick={() => {
              table.resetColumnFilters()
              table.setGlobalFilter('')
            }}
            className='h-8 px-2 lg:px-3'
          >
            重置
            <Cross2Icon className='ms-2 h-4 w-4' />
          </Button>
        )}
      </div>
      <div className='flex justify-end'>
        <DataTableViewOptions table={table} />
      </div>
    </div>
  )
}
