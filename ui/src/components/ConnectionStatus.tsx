import { useEffect, useState } from 'react'
import { getApiRuntimeConfig, getHealth } from '../api/client'

type ConnectionState =
  | { status: 'checking' }
  | { status: 'ok'; message: string }
  | { status: 'error'; message: string }

const apiConfig = getApiRuntimeConfig()

export default function ConnectionStatus() {
  const [state, setState] = useState<ConnectionState>({ status: 'checking' })

  async function checkHealth() {
    setState({ status: 'checking' })
    try {
      const health = await getHealth()
      const advisoryCount = health.advisories?.length ?? 0
      const suffix = advisoryCount > 0 ? `，${advisoryCount} 条提示` : ''
      setState({ status: 'ok', message: `后端 ${health.status}${suffix}` })
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : '后端连接失败',
      })
    }
  }

  useEffect(() => {
    void checkHealth()
  }, [])

  const classes = {
    checking: 'border-gray-200 bg-gray-50 text-gray-600',
    ok: 'border-green-200 bg-green-50 text-green-700',
    error: 'border-red-200 bg-red-50 text-red-700',
  }[state.status]

  const dotClasses = {
    checking: 'bg-gray-400',
    ok: 'bg-green-500',
    error: 'bg-red-500',
  }[state.status]

  return (
    <div className={`border-b ${classes}`}>
      <div className="max-w-7xl mx-auto px-4 py-2 flex flex-col gap-2 text-xs sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="inline-flex items-center gap-1.5 font-medium">
            <span className={`h-2 w-2 rounded-full ${dotClasses}`} />
            {state.status === 'checking' ? '正在检查后端连接…' : state.message}
          </span>
          <span>API：{apiConfig.displayBase}</span>
          <span>租户鉴权：{apiConfig.tenantTokenSource}</span>
          {!apiConfig.hasTenantToken && (
            <span className="basis-full text-red-700/80">
              缺少租户 token，请在 `ui/.env.local` 配置 `VITE_TENANT_TOKEN`。
            </span>
          )}
          {state.status === 'error' && apiConfig.hasTenantToken && (
            <span className="basis-full text-red-700/80">
              请确认后端已启动，且 `APP_SERVER_PORT` 与 Vite 代理目标一致。
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => void checkHealth()}
          className="self-start rounded border border-current px-2 py-1 hover:bg-white/60 sm:self-auto"
        >
          重新检查
        </button>
      </div>
    </div>
  )
}
