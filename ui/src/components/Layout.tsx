import { Link, Outlet, useLocation } from 'react-router-dom'
import { getHealth } from '../api/client'
import { useEffect, useState } from 'react'

type ConnState = 'checking' | 'ok' | 'error'

const HEALTH_POLL_INTERVAL = 15000

function MiniConnectionStatus() {
  const [state, setState] = useState<ConnState>('checking')

  // 周期性复检：避免后端慢启动 / 一次性瞬时失败把状态永久锁死在“离线”。
  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        await getHealth()
        if (!cancelled) setState('ok')
      } catch {
        if (!cancelled) setState('error')
      }
    }
    void check()
    const timer = setInterval(() => void check(), HEALTH_POLL_INTERVAL)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const dot =
    state === 'checking'
      ? 'bg-gray-400'
      : state === 'ok'
      ? 'bg-green-500'
      : 'bg-red-500'

  const label =
    state === 'checking' ? '检查中…' : state === 'ok' ? '后端正常' : '后端离线'

  return (
    <div className="flex items-center gap-1.5 text-xs text-gray-400">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {label}
    </div>
  )
}

interface NavLinkProps {
  to: string
  label: string
  icon: React.ReactNode
  exact?: boolean
}

function NavLink({ to, label, icon, exact }: NavLinkProps) {
  const location = useLocation()
  const active = exact ? location.pathname === to : location.pathname.startsWith(to)
  return (
    <Link
      to={to}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? 'bg-blue-50 text-blue-700'
          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
      }`}
    >
      <span className="h-5 w-5 flex-shrink-0 text-current opacity-70">{icon}</span>
      {label}
    </Link>
  )
}

export default function Layout() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 flex w-56 flex-col border-r border-gray-200 bg-white">
        {/* Brand */}
        <div className="flex h-14 items-center gap-2 border-b border-gray-200 px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-600 text-white text-xs font-bold">
            审
          </div>
          <Link to="/" className="text-sm font-semibold text-gray-800 hover:text-blue-600 transition-colors">
            企业审核平台
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          <NavLink
            to="/"
            exact
            label="任务列表"
            icon={
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            }
          />
          <NavLink
            to="/ocr"
            label="文档识别"
            icon={
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            }
          />
        </nav>

        {/* Footer: mini connection status */}
        <div className="border-t border-gray-200 px-4 py-3">
          <MiniConnectionStatus />
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col pl-56">
        <main className="flex-1 px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
