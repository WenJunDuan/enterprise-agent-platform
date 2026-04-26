import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { listTasks } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import type { AuditTask, TaskStatus } from '../types'

const LIMIT = 20

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '全部状态' },
  { value: 'accepted', label: '已接收' },
  { value: 'running', label: '审核中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
]

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN')
}

function truncate(str: string, n = 16): string {
  return str.length > n ? `${str.slice(0, n)}…` : str
}

export default function TaskList() {
  const [tasks, setTasks] = useState<AuditTask[]>([])
  const [status, setStatus] = useState<string>('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listTasks({ status: status || undefined, limit: LIMIT, offset })
      setTasks(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [status, offset])

  useEffect(() => { load() }, [load])

  function handleStatusChange(val: string) {
    setStatus(val)
    setOffset(0)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-800">审核任务列表</h1>
        <select
          value={status}
          onChange={e => handleStatusChange(e.target.value)}
          className="text-sm border border-gray-300 rounded-md px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {STATUS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-600">请求 ID</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">案例 ID</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">状态</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">进度</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">提交时间</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: 6 }).map((__, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 bg-gray-100 rounded animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))
            ) : tasks.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-gray-400">
                  暂无任务
                </td>
              </tr>
            ) : (
              tasks.map(task => (
                <tr key={task.request_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">
                    {truncate(task.request_id, 20)}
                  </td>
                  <td className="px-4 py-3 text-gray-700">
                    {task.claim_id ?? '—'}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={task.status as TaskStatus} />
                  </td>
                  <td className="px-4 py-3 text-gray-500 max-w-xs truncate">
                    {task.progress_message ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                    {formatDate(task.submitted_at)}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/tasks/${task.request_id}`}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      查看详情
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm text-gray-600">
        <span>每页 {LIMIT} 条</span>
        <div className="flex gap-2">
          <button
            onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            disabled={offset === 0}
            className="px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40 hover:bg-gray-50 transition-colors"
          >
            上一页
          </button>
          <button
            onClick={() => setOffset(offset + LIMIT)}
            disabled={tasks.length < LIMIT}
            className="px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40 hover:bg-gray-50 transition-colors"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  )
}
