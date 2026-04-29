import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { listTasks } from '../api/client'
import StatCard from '../components/StatCard'
import StatusBadge from '../components/StatusBadge'
import { formatAmount } from '../lib/reimbursementLabels'
import { clearSubmissionSummaries, readSubmissionSummaries } from '../lib/submissionSummary'
import type { AuditTask, SubmissionSummary } from '../types'

const LIMIT = 20

const STATUS_TABS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'accepted', label: '已接收' },
  { value: 'running', label: '审核中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
]

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN')
}

function truncate(str: string, n = 20): string {
  return str.length > n ? `${str.slice(0, n)}…` : str
}

export default function TaskList() {
  const [tasks, setTasks] = useState<AuditTask[]>([])
  const [summaries, setSummaries] = useState<Record<string, SubmissionSummary>>({})
  const [status, setStatus] = useState<string>('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listTasks({ status: status || undefined, limit: LIMIT, offset })
      setTasks(data)
      setSummaries(readSubmissionSummaries())
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [status, offset])

  useEffect(() => { load() }, [load])

  const rows = useMemo(
    () => tasks.map(task => ({ task, summary: summaries[task.request_id] })),
    [summaries, tasks],
  )

  // Stats computed from listTasks data
  const stats = useMemo(() => {
    const total = tasks.length
    const pending = tasks.filter(t => t.status === 'accepted' || t.status === 'running').length
    const completed = tasks.filter(t => t.status === 'completed').length
    const passRate = total > 0 ? Math.round((completed / total) * 100) : 0
    return { total, pending, passRate }
  }, [tasks])

  function handleStatusChange(val: string) {
    setStatus(val)
    setOffset(0)
  }

  function handleClearSummaries() {
    clearSubmissionSummaries()
    setSummaries({})
    setNotice('已清空本机提交摘要；列表将按后端紧凑任务字段降级展示')
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">报销审核任务</h1>
          <p className="text-sm text-gray-500 mt-1">
            本机提交过的任务会叠加业务摘要与异常标签
          </p>
        </div>
        <Link
          to="/submit"
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          + 新建报销
        </Link>
      </div>

      {/* Stat cards */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard title="今日返回任务数" value={stats.total} subtitle="当前页" />
        <StatCard title="待审核" value={stats.pending} colorClass="text-amber-600" />
        <StatCard
          title="完成率"
          value={`${stats.passRate}%`}
          subtitle={`${tasks.filter(t => t.status === 'completed').length} / ${stats.total} 已完成`}
          colorClass="text-green-700"
        />
      </div>

      {/* Status tabs + toolbar */}
      <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-1 overflow-x-auto">
          {STATUS_TABS.map(tab => (
            <button
              key={tab.value}
              type="button"
              onClick={() => handleStatusChange(tab.value)}
              className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                status === tab.value
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={load}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            刷新
          </button>
          <button
            type="button"
            onClick={handleClearSummaries}
            disabled={Object.keys(summaries).length === 0}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            清空摘要
          </button>
        </div>
      </div>

      {notice && (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded-md text-sm text-blue-700">{notice}</div>
      )}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">{error}</div>
      )}

      {/* Task table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">单号 / 请求 ID</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">状态</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">金额概要</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">提交时间</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 5 }).map((__, j) => (
                      <td key={j} className="px-4 py-4">
                        <div className="h-4 bg-gray-100 rounded animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-gray-400">
                    暂无任务，可新建报销申请
                  </td>
                </tr>
              ) : (
                rows.map(({ task, summary }) => (
                  <tr key={task.request_id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-mono text-xs text-gray-500">{truncate(task.request_id)}</p>
                      <p className="font-medium text-gray-800 mt-0.5">
                        {summary?.form.case_id ?? task.claim_id ?? '—'}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={task.status} />
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      {summary
                        ? formatAmount(summary.form.total_amount, summary.form.currency)
                        : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                      {formatDate(task.submitted_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
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
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-gray-600">
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
