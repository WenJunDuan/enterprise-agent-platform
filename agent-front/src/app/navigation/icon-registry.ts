import { iconNames, type IconName } from 'lucide-react/dynamic'

const iconNameSet = new Set<IconName>(iconNames)

const LEGACY_BACKEND_ICON_ALIASES: Record<string, IconName> = {
  system: 'settings',
  monitor: 'monitor-cog',
  user: 'users',
  role: 'users-round',
  menu: 'list-tree',
  dept: 'folder-tree',
  dict: 'book-open-text',
  file: 'files',
  online: 'badge-check',
  operlog: 'logs',
  loginlog: 'logs',
  cache: 'database-zap',
  server: 'server-cog',
  peoples: 'users-round',
  'tree-table': 'list-tree',
  tree: 'folder-tree',
  edit: 'settings-2',
  upload: 'files',
  form: 'logs',
  logininfor: 'logs',
  redis: 'database-zap',
}

function normalizeIconToken(iconName: string) {
  return iconName
    .trim()
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1-$2')
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[_\s]+/g, '-')
    .replace(/[^a-zA-Z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .toLowerCase()
}

export function normalizeBackendIconName(
  iconName?: string | null
): IconName | undefined {
  if (!iconName) {
    return undefined
  }

  const normalizedIconName = normalizeIconToken(iconName)
  if (!normalizedIconName) {
    return undefined
  }

  const resolvedIconName =
    LEGACY_BACKEND_ICON_ALIASES[normalizedIconName] ?? normalizedIconName

  if (!iconNameSet.has(resolvedIconName as IconName)) {
    return undefined
  }

  return resolvedIconName as IconName
}
