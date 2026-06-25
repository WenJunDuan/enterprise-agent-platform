import { useSyncExternalStore } from 'react'
import type { NavGroup, NavItem } from '@/components/layout/types'

const STORAGE_KEY = 'enterprise-agent-front:navigation-menu-visibility:v1'
const CHANGE_EVENT = 'enterprise-agent-front:navigation-menu-visibility-change'

export type NavigationMenuVisibility = {
  groups: Record<string, boolean>
  items: Record<string, boolean>
}

export const DEFAULT_NAVIGATION_MENU_VISIBILITY: NavigationMenuVisibility = {
  groups: {},
  items: {},
}

let initialized = false
let currentSnapshot = DEFAULT_NAVIGATION_MENU_VISIBILITY

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizeFlagRecord(value: unknown) {
  if (!isRecord(value)) {
    return {}
  }

  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, boolean] => {
      const [, flag] = entry
      return typeof flag === 'boolean'
    })
  )
}

export function normalizeNavigationMenuVisibility(
  value: unknown
): NavigationMenuVisibility {
  if (!isRecord(value)) {
    return DEFAULT_NAVIGATION_MENU_VISIBILITY
  }

  return {
    groups: normalizeFlagRecord(value.groups),
    items: normalizeFlagRecord(value.items),
  }
}

function getStorage() {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    return window.localStorage
  } catch {
    return null
  }
}

function hasVisibilityOverrides(visibility: NavigationMenuVisibility) {
  return (
    Object.keys(visibility.groups).length > 0 ||
    Object.keys(visibility.items).length > 0
  )
}

function readNavigationMenuVisibility() {
  const storage = getStorage()
  if (!storage) {
    return DEFAULT_NAVIGATION_MENU_VISIBILITY
  }

  try {
    const rawValue = storage.getItem(STORAGE_KEY)
    return normalizeNavigationMenuVisibility(
      rawValue ? JSON.parse(rawValue) : null
    )
  } catch {
    return DEFAULT_NAVIGATION_MENU_VISIBILITY
  }
}

function emitChange() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(CHANGE_EVENT))
  }
}

function writeNavigationMenuVisibility(visibility: NavigationMenuVisibility) {
  const nextSnapshot = normalizeNavigationMenuVisibility(visibility)
  currentSnapshot = nextSnapshot
  initialized = true

  const storage = getStorage()
  if (storage) {
    try {
      if (hasVisibilityOverrides(nextSnapshot)) {
        storage.setItem(STORAGE_KEY, JSON.stringify(nextSnapshot))
      } else {
        storage.removeItem(STORAGE_KEY)
      }
    } catch {
      // Menu visibility remains in memory when localStorage is unavailable.
    }
  }

  emitChange()
}

function updateNavigationMenuVisibility(
  updater: (visibility: NavigationMenuVisibility) => NavigationMenuVisibility
) {
  const baseSnapshot = initialized
    ? currentSnapshot
    : readNavigationMenuVisibility()
  writeNavigationMenuVisibility(updater(baseSnapshot))
}

function getSnapshot() {
  if (typeof window === 'undefined') {
    return DEFAULT_NAVIGATION_MENU_VISIBILITY
  }

  if (!initialized) {
    currentSnapshot = readNavigationMenuVisibility()
    initialized = true
  }

  return currentSnapshot
}

function getServerSnapshot() {
  return DEFAULT_NAVIGATION_MENU_VISIBILITY
}

function subscribe(onStoreChange: () => void) {
  if (typeof window === 'undefined') {
    return () => {}
  }

  function handleStorage(event: StorageEvent) {
    if (event.key && event.key !== STORAGE_KEY) {
      return
    }

    currentSnapshot = readNavigationMenuVisibility()
    initialized = true
    onStoreChange()
  }

  window.addEventListener(CHANGE_EVENT, onStoreChange)
  window.addEventListener('storage', handleStorage)

  return () => {
    window.removeEventListener(CHANGE_EVENT, onStoreChange)
    window.removeEventListener('storage', handleStorage)
  }
}

export function useNavigationMenuVisibility() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}

export function getNavigationMenuItemKey(
  groupTitle: string,
  item: { title: string; url?: unknown }
) {
  return `${groupTitle}:${String(item.url ?? item.title)}`
}

export function isNavigationMenuGroupVisible(
  visibility: NavigationMenuVisibility,
  groupTitle: string
) {
  return visibility.groups[groupTitle] !== false
}

export function isNavigationMenuItemVisible(
  visibility: NavigationMenuVisibility,
  groupTitle: string,
  item: { title: string; url?: unknown }
) {
  return visibility.items[getNavigationMenuItemKey(groupTitle, item)] !== false
}

function setFlag(
  current: Record<string, boolean>,
  key: string,
  visible: boolean
) {
  const next = { ...current }

  if (visible) {
    delete next[key]
  } else {
    next[key] = false
  }

  return next
}

export function setNavigationMenuGroupVisible(
  groupTitle: string,
  visible: boolean
) {
  updateNavigationMenuVisibility((visibility) => ({
    ...visibility,
    groups: setFlag(visibility.groups, groupTitle, visible),
  }))
}

export function setNavigationMenuItemVisible(
  groupTitle: string,
  item: { title: string; url?: unknown },
  visible: boolean
) {
  updateNavigationMenuVisibility((visibility) => ({
    ...visibility,
    items: setFlag(
      visibility.items,
      getNavigationMenuItemKey(groupTitle, item),
      visible
    ),
  }))
}

export function resetNavigationMenuVisibility() {
  writeNavigationMenuVisibility(DEFAULT_NAVIGATION_MENU_VISIBILITY)
}

function filterNavigationItem(
  groupTitle: string,
  item: NavItem,
  visibility: NavigationMenuVisibility
): NavItem | null {
  if (!isNavigationMenuItemVisible(visibility, groupTitle, item)) {
    return null
  }

  if (!item.items) {
    return item
  }

  const items = item.items.filter((childItem) =>
    isNavigationMenuItemVisible(visibility, groupTitle, childItem)
  )

  return items.length > 0 ? { ...item, items } : null
}

export function filterNavigationGroupsByVisibility(
  groups: NavGroup[],
  visibility: NavigationMenuVisibility = DEFAULT_NAVIGATION_MENU_VISIBILITY
) {
  return groups.flatMap((group) => {
    if (!isNavigationMenuGroupVisible(visibility, group.title)) {
      return []
    }

    const items = group.items
      .map((item) => filterNavigationItem(group.title, item, visibility))
      .filter((item): item is NavItem => item !== null)

    return items.length > 0 ? [{ ...group, items }] : []
  })
}
