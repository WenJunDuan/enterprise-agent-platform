import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { listTasks } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import {
  SCENARIO_FLAG_LABELS,
  formatAmount,
  formatFileSize,
} from '../lib/reimbursementLabels'
import { readSubmissionSummaries } from '../lib/submissionSummary'
import type { AuditTask, SubmissionSummary } from '../types'

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

function summarizeAttachments(summary: SubmissionSummary): string {
  const totalSize = summary.attachments.reduce((sum, item) => sum + item.size, 0)
  return `${summary.attachments.length} 个 · ${formatFileSize(totalSize)}`
}

function buildSearchText(task: AuditTask, summary?: SubmissionSummary): string {
  const base = [
    task.request_id,
    task.claim_id ?? '',
    task.status,
    task.progress_message ?? '',
    task.error_detail ?? '',
  ]
  if (!summary) return base.join(' ').toLowerCase()
  return [
    ...base,
    summary.form.case_id,
    summary.form.applicant_name,
    summary.form.department,
    summary.form.cost_center,
    summary.form.project_name,
    summary.form.customer_name,
    summary.form.expense_type,
    summary.form.total_amount,
    summary.form.scenario_flags.map(flag => SCENARIO_FLAG_LABELS[flag]).join(' '),
    summary.attachments.map(item => item.name).join(' '),
  ].join(' ').toLowerCase()
}

export default function TaskList() {
  const [tasks, setTasks] = useState<AuditTask[]>([])
  const [summaries, setSummaries] = useState<Record<string, SubmissionSummary>>({})
  const [status, setStatus] = useState<string>('')
  const [expenseType, setExpenseType] = useState<string>('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  const expenseTypeOptions = useMemo(
    () => Array.from(new Set(rows.map(row => row.summary?.form.expense_type).filter(Boolean))),
    [rows],
  )

  const filteredRows = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()
    return rows.filter(row => {
      if (expenseType && row.summary?.form.expense_type !== expenseType) return false
      if (!normalizedSearch) return true
      return buildSearchText(row.task, row.summary).includes(normalizedSearch)
    })
  }, [expenseType, rows, search])

  const stats = useMemo(() => {
    const withSummary = rows.filter(row => row.summary).length
    const running = tasks.filter(task => task.status === 'accepted' || task.status === 'running').length
    const completed = tasks.filter(task => task.status === 'completed').length
    const failed = tasks.filter(task => task.status === 'failed').length
    const flagged = rows.filter(row => (row.summary?.form.scenario_flags.length ?? 0) > 0).length
    return { total: tasks.length, withSummary, running, completed, failed, flagged }
  }, [rows, tasks])

  function handleStatusChange(val: string) {
    setStatus(val)
    setOffset(0)
  }

  function handleExpenseTypeChange(val: string) {
    setExpenseType(val)
    setOffset(0)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">报销审核任务列表</h1>
          <p className="text-sm text-gray-500 mt-1">
            后端返回紧凑任务数据；本机提交过的任务会叠加业务摘要、附件和异常标签。
          </p>
        </div>
        <Link
          to="/submit"
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          新建复杂报销
        </Link>
      </div>

      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-500">当前页任务</p>
          <p className="mt-1 text-2xl font-semibold text-gray-900">{stats.total}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-500">本地摘要</p>
          <p className="mt-1 text-2xl font-semibold text-blue-700">{stats.withSummary}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-500">审核中</p>
          <p className="mt-1 text-2xl font-semibold text-amber-600">{stats.running}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-500">已完成</p>
          <p className="mt-1 text-2xl font-semibold text-green-700">{stats.completed}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-500">失败</p>
          <p className="mt-1 text-2xl font-semibold text-red-700">{stats.failed}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-500">异常标签</p>
          <p className="mt-1 text-2xl font-semibold text-orange-700">{stats.flagged}</p>
        </div>
      </div>

      <div className="grid gap-3 rounded-xl border border-gray-200 bg-white p-4 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto]">
        <input
          value={search}
          onChange={event => setSearch(event.target.value)}
          placeholder="搜索请求 ID、报销单号、申请人、部门、项目、附件或异常标签"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={status}
          onChange={event => handleStatusChange(event.target.value)}
          className="text-sm border border-gray-300 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {STATUS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select
          value={expenseType}
          onChange={event => handleExpenseTypeChange(event.target.value)}
          className="text-sm border border-gray-300 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">全部费用类型</option>
          {expenseTypeOptions.map(option => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={load}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          刷新
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">请求 / 单号</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">业务摘要</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">金额 / 附件</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">异常</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">状态</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">提交时间</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 7 }).map((__, j) => (
                      <td key={j} className="px-4 py-4">
                        <div className="h-4 bg-gray-100 rounded animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                    暂无匹配任务；可调整筛选条件或新建复杂报销申请
                  </td>
                </tr>
              ) : (
                filteredRows.map(({ task, summary }) => (
                  <tr key={task.request_id} className="hover:bg-gray-50 transition-colors align-top">
                    <td className="px-4 py-4">
                      <p className="font-mono text-xs text-gray-700">{truncate(task.request_id, 20)}</p>
                      <p className="mt-1 font-mono text-xs text-gray-400">{summary?.form.case_id ?? task.claim_id ?? '无业务单号'}</p>
                    </td>
                    <td className="px-4 py-4">
                      {summary ? (
                        <div className="space-y-1">
                          <p className="font-medium text-gray-800">
                            {summary.form.expense_type} · {summary.form.applicant_name}
                          </p>
                          <p className="text-xs text-gray-500">
                            {summary.form.department || '未填部门'} / {summary.form.project_name || summary.form.customer_name || '未填项目'}
                          </p>
                          <p className="line-clamp-2 text-xs text-gray-500">
                            {summary.form.reimbursement_reason || '无报销事由'}
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <p className="font-medium text-gray-600">{task.claim_id ?? '后端历史任务'}</p>
                          <p className="text-xs text-gray-400">未命中本机提交摘要，展示后端紧凑字段</p>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      {summary ? (
                        <div className="space-y-1">
                          <p className="font-medium text-gray-800">{formatAmount(summary.form.total_amount, summary.form.currency)}</p>
                          <p className="text-xs text-gray-500">{summarizeAttachments(summary)}</p>
                        </div>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      {summary && summary.form.scenario_flags.length > 0 ? (
                        <div className="flex max-w-[260px] flex-wrap gap-1.5">
                          {summary.form.scenario_flags.slice(0, 3).map(flag => (
                            <span key={flag} className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
                              {SCENARIO_FLAG_LABELS[flag]}
                            </span>
                          ))}
                          {summary.form.scenario_flags.length > 3 && (
                            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                              +{summary.form.scenario_flags.length - 3}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400">无异常标签</span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <StatusBadge status={task.status} />
                      <p className="mt-2 max-w-[180px] truncate text-xs text-gray-500">
                        {task.progress_message ?? task.error_detail ?? '—'}
                      </p>
                    </td>
                    <td className="px-4 py-4 text-gray-500 whitespace-nowrap">
                      {formatDate(task.submitted_at)}
                    </td>
                    <td className="px-4 py-4">
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

      <div className="mt-4 flex items-center justify-between text-sm text-gray-600">
        <span>后端分页：每页 {LIMIT} 条；当前筛选后显示 {filteredRows.length} 条</span>
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
