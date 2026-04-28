import { Link, Outlet } from 'react-router-dom'
import ConnectionStatus from './ConnectionStatus'

export default function Layout() {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/" className="text-lg font-semibold text-gray-800 hover:text-blue-600 transition-colors">
            企业审核平台
          </Link>
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="text-sm text-gray-600 hover:text-blue-600 transition-colors"
            >
              任务列表
            </Link>
            <Link
              to="/submit"
              className="text-sm bg-blue-600 text-white px-3 py-1.5 rounded-md hover:bg-blue-700 transition-colors"
            >
              新建报销
            </Link>
          </div>
        </div>
      </nav>
      <ConnectionStatus />
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
