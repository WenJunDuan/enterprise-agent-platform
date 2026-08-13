import {
  constructTable,
  tableFeatures,
  type ColumnDef,
} from '@tanstack/react-table'
import { storeReactivityBindings } from '@tanstack/table-core/store-reactivity-bindings'
import { describe, expect, test } from 'bun:test'
import { appTableFeatures } from './table-features'

// The React adapter injects its own reactivity inside `useTable`; a headless table has to
// bring the vanilla TanStack Store bindings itself.
const headlessFeatures = tableFeatures({
  ...appTableFeatures,
  coreReactivityFeature: storeReactivityBindings(),
})

type AppTableFeatures = typeof headlessFeatures

type Person = {
  id: string
  name: string
  status: string
}

const people: Person[] = [
  { id: '1', name: 'ada', status: 'active' },
  { id: '2', name: 'bob', status: 'blocked' },
  { id: '3', name: 'cid', status: 'active' },
  { id: '4', name: 'dan', status: 'active' },
]

/** Mirrors the app's own multi-select column filter (see audit-tasks-page). */
function matchesSelectedValues(
  row: { getValue: (columnId: string) => unknown },
  columnId: string,
  filterValue: unknown
) {
  const selected = Array.isArray(filterValue) ? filterValue : []
  return selected.length === 0 || selected.includes(row.getValue(columnId))
}

const columns: ColumnDef<AppTableFeatures, Person, unknown>[] = [
  { id: 'name', accessorKey: 'name', filterFn: 'includesString' },
  { id: 'status', accessorKey: 'status', filterFn: matchesSelectedValues },
]

function makeTable(options: {
  manualPagination?: boolean
  manualFiltering?: boolean
  initialState?: Parameters<
    typeof constructTable<AppTableFeatures, Person>
  >[0]['initialState']
}) {
  return constructTable<AppTableFeatures, Person>({
    features: headlessFeatures,
    data: people,
    columns,
    getRowId: (row) => row.id,
    ...options,
  })
}

describe('appTableFeatures', () => {
  test('exposes the core row model without extra configuration', () => {
    const table = makeTable({})

    expect(table.getRowModel().rows.map((row) => row.id)).toEqual([
      '1',
      '2',
      '3',
      '4',
    ])
  })

  test('filters rows client-side when the table does not opt into manual filtering', () => {
    const table = makeTable({
      initialState: { columnFilters: [{ id: 'status', value: ['active'] }] },
    })

    expect(table.getRowModel().rows.map((row) => row.id)).toEqual([
      '1',
      '3',
      '4',
    ])
  })

  test('leaves rows untouched when the table declares manual filtering', () => {
    const table = makeTable({
      manualFiltering: true,
      initialState: { columnFilters: [{ id: 'status', value: ['active'] }] },
    })

    expect(table.getRowModel().rows).toHaveLength(4)
  })

  test('paginates rows client-side when the table does not opt into manual pagination', () => {
    const table = makeTable({
      initialState: { pagination: { pageIndex: 1, pageSize: 2 } },
    })

    expect(table.getRowModel().rows.map((row) => row.id)).toEqual(['3', '4'])
  })

  test('leaves rows untouched when the table declares manual pagination', () => {
    const table = makeTable({
      manualPagination: true,
      initialState: { pagination: { pageIndex: 1, pageSize: 2 } },
    })

    expect(table.getRowModel().rows).toHaveLength(4)
  })

  test('provides faceted unique values used by the faceted filter component', () => {
    const table = makeTable({})
    const facets = table.getColumn('status')?.getFacetedUniqueValues()

    expect(facets?.get('active')).toBe(3)
    expect(facets?.get('blocked')).toBe(1)
  })

  test('keeps column visibility, row selection and global filter state slices available', () => {
    const table = makeTable({})

    expect(table.store.state.columnVisibility).toEqual({})
    expect(table.store.state.rowSelection).toEqual({})
    expect(table.store.state.globalFilter).toBeUndefined()
    expect(table.getColumn('name')?.getIsVisible()).toBe(true)
  })

  test('exposes sorting APIs but does not reorder rows client-side', () => {
    const table = makeTable({})
    const column = table.getColumn('name')

    expect(column?.getCanSort()).toBe(true)
    column?.toggleSorting(true)

    expect(table.store.state.sorting).toEqual([{ id: 'name', desc: true }])
    expect(table.getRowModel().rows.map((row) => row.id)).toEqual([
      '1',
      '2',
      '3',
      '4',
    ])
  })
})
