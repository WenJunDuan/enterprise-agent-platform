import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getTask, getTaskResult } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import type { AuditTask, AuditResult, Verdict } from '../types'

const POLL_INTERVAL = 3000

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN')
}

const VERDICT_CONFIG: Record<Verdict, { label: string; classes: string }> = {
  approved: { label: '通过', classes: 'text-green-700 bg-green-50 border-green-200' },
  rejected: { label: '拒绝', classes: 'text-red-700 bg-red-50 border-red-200' },
  manual_review: { label: '待人工复核', classes: 'text-yellow-700 bg-yellow-50 border-yellow-200' },
}

function RiskBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score))
  const color = pct >= 70 ? 'bg-red-500' : pct >= 40 ? 'bg-yellow-400' : 'bg-green-500'
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-medium text-gray-700 w-8 text-right">{pct}</span>
    </div>
  )
}

function ResultSection({ result }: { result: AuditResult }) {
  const [showRaw, setShowRaw] = useState(false)
  const verdict = result.verdict
  const verdictCfg = verdict ? VERDICT_CONFIG[verdict] : null

  return (
    <div className="space-y-4">
      <h2 className="text-base font-semibold text-gray-800">审核结果</h2>

      {verdictCfg && (
        <div className={`inline-flex items-center px-4 py-2 rounded-lg border text-sm font-medium ${verdictCfg.classes}`}>
          审核结论：{verdictCfg.label}
        </div>
      )}

      {result.risk_score != null && (
        <div>
          <p className="text-sm text-gray-600 mb-1">风险评分</p>
          <RiskBar score={result.risk_score} />
        </div>
      )}

      {result.claim_id && (
        <div>
          <p className="text-sm text-gray-500">案例 ID</p>
          <p className="text-sm text-gray-800 font-mono">{result.claim_id}</p>
        </div>
      )}

      {result.summary && (
        <div>
          <p className="text-sm text-gray-500 mb-1">摘要</p>
          <p className="text-sm text-gray-800 leading-relaxed">{result.summary}</p>
        </div>
      )}

      {result.manual_review_reason && (
        <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
          <p className="text-xs text-yellow-600 font-medium mb-1">人工复核原因</p>
          <p className="text-sm text-yellow-800">{result.manual_review_reason}</p>
        </div>
      )}

      {result.policy_refs && result.policy_refs.length > 0 && (
        <div>
          <p className="text-sm text-gray-500 mb-1">政策依据</p>
          <ul className="space-y-1">
            {result.policy_refs.map((ref, i) => (
              <li key={i} className="text-sm text-gray-700 flex items-start gap-1.5">
                <span className="text-blue-400 mt-0.5">•</span>
                {ref}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <button
          onClick={() => setShowRaw(v => !v)}
          className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          {showRaw ? '收起原始数据' : '查看原始 JSON'}
        </button>
        {showRaw && (
          <pre className="mt-2 p-3 bg-gray-50 border border-gray-200 rounded-md text-xs text-gray-600 overflow-auto max-h-64">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>()
  const [task, setTask] = useState<AuditTask | null>(null)
  const [result, setResult] = useState<AuditResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function stopPolling() {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  async function fetchTask() {
    if (!id) return
    try {
      const data = await getTask(id)
      setTask(data)
      if (data.status === 'completed') {
        stopPolling()
        try {
          const res = await getTaskResult(id)
          setResult(res)
        } catch {
          // result fetch failure is non-fatal
        }
      } else if (data.status === 'failed') {
        stopPolling()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
      stopPolling()
    }
  }

  useEffect(() => {
    if (!id) return
    setLoading(true)
    fetchTask().finally(() => setLoading(false))

    timerRef.current = setInterval(() => {
      fetchTask()
    }, POLL_INTERVAL)

    return () => stopPolling()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-6 bg-gray-100 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div>
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-sm text-red-700 mb-4">
          {error}
        </div>
        <Link to="/" className="text-sm text-blue-600 hover:underline">← 返回任务列表</Link>
      </div>
    )
  }

  if (!task) return null

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <Link to="/" className="text-sm text-gray-500 hover:text-blue-600 transition-colors">
          ← 返回任务列表
        </Link>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-gray-400 mb-1">请求 ID</p>
            <p className="font-mono text-sm text-gray-800 break-all">{task.request_id}</p>
          </div>
          <StatusBadge status={task.status} />
        </div>

        {task.status === 'running' && task.progress_message && (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-md text-sm text-blue-700">
            {task.progress_message}
          </div>
        )}

        <div className="grid grid-cols-3 gap-4">
          <div>
            <p className="text-xs text-gray-400 mb-1">提交时间</p>
            <p className="text-sm text-gray-700">{formatDate(task.submitted_at)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">开始时间</p>
            <p className="text-sm text-gray-700">{formatDate(task.started_at)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">完成时间</p>
            <p className="text-sm text-gray-700">{formatDate(task.finished_at)}</p>
          </div>
        </div>

        {task.status === 'failed' && task.error_detail && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-xs text-red-500 font-medium mb-1">错误详情</p>
            <p className="text-sm text-red-800">{task.error_detail}</p>
          </div>
        )}
      </div>

      {task.status === 'completed' && result && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <ResultSection result={result} />
        </div>
      )}

      {task.status === 'completed' && !result && (
        <div className="p-4 bg-gray-50 border border-gray-200 rounded-md text-sm text-gray-500">
          结果数据暂不可用
        </div>
      )}
    </div>
  )
}
