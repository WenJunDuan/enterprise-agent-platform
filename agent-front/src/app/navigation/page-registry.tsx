import { type NavigateFn } from '@/hooks/use-table-url-state'
import { CacheMonitorPage } from '@/features/monitor/cache'
import { LoginLogPage } from '@/features/monitor/login-log'
import { OperLogPage } from '@/features/monitor/oper-log'
import { OnlineUserPage } from '@/features/monitor/online'
import { ServerMonitorPage } from '@/features/monitor/server'
import { DepartmentManagementPage } from '@/features/system/dept'
import { DictManagementPage } from '@/features/system/dict'
import { FileManagementPage } from '@/features/system/file'
import { MenuManagementPage } from '@/features/system/menu'
import { RoleManagementPage } from '@/features/system/role'
import { UserManagementPage } from '@/features/system/user'

export type BackendPageProps = {
  search: Record<string, unknown>
  navigate: NavigateFn
}

export type BackendPageDefinition = {
  backendComponent: string
  fullPath: string
  render: (props: BackendPageProps) => React.JSX.Element
}

const backendPageDefinitions: BackendPageDefinition[] = [
  {
    backendComponent: 'system/user/index',
    fullPath: '/system/user',
    render: (props) => <UserManagementPage {...props} />,
  },
  {
    backendComponent: 'system/role/index',
    fullPath: '/system/role',
    render: (props) => <RoleManagementPage {...props} />,
  },
  {
    backendComponent: 'system/menu/index',
    fullPath: '/system/menu',
    render: () => <MenuManagementPage />,
  },
  {
    backendComponent: 'system/dept/index',
    fullPath: '/system/dept',
    render: () => <DepartmentManagementPage />,
  },
  {
    backendComponent: 'system/dict/index',
    fullPath: '/system/dict',
    render: () => <DictManagementPage />,
  },
  {
    backendComponent: 'system/file/index',
    fullPath: '/system/file',
    render: (props) => <FileManagementPage {...props} />,
  },
  {
    backendComponent: 'monitor/online/index',
    fullPath: '/monitor/online',
    render: () => <OnlineUserPage />,
  },
  {
    backendComponent: 'monitor/operlog/index',
    fullPath: '/monitor/operlog',
    render: (props) => <OperLogPage {...props} />,
  },
  {
    backendComponent: 'monitor/loginlog/index',
    fullPath: '/monitor/loginlog',
    render: (props) => <LoginLogPage {...props} />,
  },
  {
    backendComponent: 'monitor/server/index',
    fullPath: '/monitor/server',
    render: () => <ServerMonitorPage />,
  },
  {
    backendComponent: 'monitor/cache/index',
    fullPath: '/monitor/cache',
    render: () => <CacheMonitorPage />,
  },
]

const pageDefinitionByComponent = new Map(
  backendPageDefinitions.map((definition) => [
    definition.backendComponent,
    definition,
  ])
)

const pageDefinitionByPath = new Map(
  backendPageDefinitions.map((definition) => [definition.fullPath, definition])
)

export function getBackendPageByComponent(component?: string | null) {
  return component ? pageDefinitionByComponent.get(component) : undefined
}

export function getBackendPageByPath(pathname: string) {
  return pageDefinitionByPath.get(pathname)
}

export function isSupportedBackendComponent(component?: string | null) {
  return Boolean(getBackendPageByComponent(component))
}
