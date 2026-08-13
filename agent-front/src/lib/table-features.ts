import {
  columnFacetingFeature,
  columnFilteringFeature,
  columnVisibilityFeature,
  createFacetedRowModel,
  createFacetedUniqueValues,
  createFilteredRowModel,
  createPaginatedRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  tableFeatures,
} from '@tanstack/react-table'

/**
 * The feature set shared by every data table in the app.
 *
 * TanStack Table v9 only exposes an API when its feature is registered here, so this
 * object lists exactly the features the app's tables and shared `components/data-table/*`
 * components call into.
 *
 * `sortedRowModel` is deliberately absent: no table registered `getSortedRowModel()` under
 * v8, so sorting only ever toggled state without reordering rows. Registering it would
 * change on-screen behaviour rather than preserve it.
 */
export const appTableFeatures = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  columnFacetingFeature,
  columnVisibilityFeature,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  filteredRowModel: createFilteredRowModel(),
  facetedRowModel: createFacetedRowModel(),
  facetedUniqueValues: createFacetedUniqueValues(),
  paginatedRowModel: createPaginatedRowModel(),
  filterFns: { includesString: filterFn_includesString },
})

export type AppTableFeatures = typeof appTableFeatures
