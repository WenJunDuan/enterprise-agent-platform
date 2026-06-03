import { useState, useEffect, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getTask, getTaskResult, retryTask, deleteTask } from '../api/client'
import { getSubmissionSummary } from '../lib/submissionSummary'
import { formatAmount } from '../lib/reimbursementLabels'
import Accordion from '../components/Accordion'
import RiskRadar from '../components/RiskRadar'
import { SkeletonCard } from '../components/Skeleton'
import type { AuditTask, AuditResult, SubmissionSummary, Verdict } from '../types'

const POLL_INTERVAL = 3000

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN')
}

const VERDICT_CONFIG: Record<Verdict, { label: string; bg: string; text: string }> = {
  approved: { label: '通过', bg: 'bg-green-50', text: 'text-green-700' },
  rejected: { label: '拒绝', bg: 'bg-red-50', text: 'text-red-700' },
  manual_review: { label: '待人工复核', bg: 'bg-yellow-50', text: 'text-yellow-700' },
}

function RiskScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score))
  const color = pct >= 70 ? 'bg-red-500' : pct >= 40 ? 'bg-yellow-400' : 'bg-green-500'
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-semibold text-gray-700 w-8 text-right">{pct}</span>
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
    >
      {copied ? (
        <svg className="h-3.5 w-3.5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      )}
      {copied ? '已复制' : '复制 ID'}
    </button>
  )
}

function StatusBanner({ task }: { task: AuditTask }) {
  if (task.status === 'running') {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-blue-200 bg-blue-50 px-5 py-4">
        <span className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
        </span>
        <p className="text-sm font-medium text-blue-800">
          审核中{task.progress_message ? `：${task.progress_message}` : '…'}
        </p>
      </div>
    )
  }
  if (task.status === 'accepted') {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 px-5 py-4">
        <span className="h-2.5 w-2.5 rounded-full bg-gray-400" />
        <p className="text-sm font-medium text-gray-700">等待处理中</p>
      </div>
    )
  }
  if (task.status === 'failed') {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4">
        <p className="text-sm font-semibold text-red-800">审核失败</p>
        {task.error_detail && (
          <p className="mt-1 text-xs text-red-600">{task.error_detail}</p>
        )}
      </div>
    )
  }
  return null
}

function ConclusionCard({ result }: { result: AuditResult }) {
  const verdict = result.verdict
  const cfg = verdict ? VERDICT_CONFIG[verdict] : null
  const riskScore = result.risk_score ?? null

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-xs font-medium text-gray-400 mb-1">审核结论</p>
          <p className="text-lg font-semibold text-gray-900 leading-snug">
            {result.conclusion ?? result.explanation?.slice(0, 80) ?? '—'}
          </p>
        </div>
        {cfg && (
          <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold border ${cfg.bg} ${cfg.text} border-current/20 shrink-0`}>
            {cfg.label}
          </span>
        )}
      </div>

      {result.explanation && result.conclusion && result.explanation !== result.conclusion && (
        <p className="text-sm text-gray-600 leading-relaxed">{result.explanation}</p>
      )}

      {riskScore !== null && (
        <div>
          <p className="text-xs font-medium text-gray-400 mb-2">风险评分</p>
          <RiskScoreBar score={riskScore} />
        </div>
      )}

      {result.manual_review_reason && (
        <div className="rounded-lg bg-yellow-50 border border-yellow-200 px-4 py-3">
          <p className="text-xs font-medium text-yellow-700">
            人工复核原因：{result.manual_review_reason}
          </p>
        </div>
      )}
    </div>
  )
}

function RiskDimensionCard({ dimensions }: { dimensions: { name: string; score: number }[] }) {
  if (!dimensions || dimensions.length === 0) return null
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <p className="text-xs font-medium text-gray-400 mb-4">风险维度</p>
      <div className="flex items-center gap-6">
        <RiskRadar dimensions={dimensions} />
        <ul className="flex-1 space-y-2">
          {dimensions.map(d => {
            const color = d.score >= 7 ? 'text-red-600' : d.score >= 4 ? 'text-yellow-600' : 'text-green-600'
            return (
              <li key={d.name} className="flex items-center justify-between text-sm">
                <span className="text-gray-600">
                  {{ invoice: '发票', amount: '金额', approval: '审批', budget: '预算', anomaly: '异常' }[d.name] ?? d.name}
                </span>
                <span className={`font-semibold ${color}`}>{d.score}/10</span>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

function EvidenceCard({ result }: { result: AuditResult }) {
  const hasReasons = result.reasons && result.reasons.length > 0
  const hasPolicyRefs = result.policy_refs && result.policy_refs.length > 0
  const hasEvidence = result.evidence_chain && result.evidence_chain.length > 0

  if (!hasReasons && !hasPolicyRefs && !hasEvidence) return null

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-3">
      <p className="text-xs font-medium text-gray-400">证据与策略</p>

      {hasReasons && (
        <Accordion title={`审核理由（${result.reasons!.length} 条）`} defaultOpen>
          <ul className="space-y-2">
            {result.reasons!.map((r, i) => (
              <li key={i} className="flex gap-2 text-sm text-gray-700">
                <span className="mt-0.5 shrink-0 h-4 w-4 rounded-full bg-gray-100 text-center text-xs leading-4 text-gray-500">{i + 1}</span>
                {r}
              </li>
            ))}
          </ul>
        </Accordion>
      )}

      {hasPolicyRefs && (
        <Accordion title={`策略引用（${result.policy_refs!.length} 条）`}>
          <ul className="space-y-1.5">
            {result.policy_refs!.map((p, i) => (
              <li key={i} className="text-sm text-gray-600 flex gap-2">
                <span className="text-blue-400 shrink-0">§</span>{p}
              </li>
            ))}
          </ul>
        </Accordion>
      )}

      {hasEvidence && (
        <Accordion title={`证据链（${result.evidence_chain!.length} 条）`}>
          <ul className="space-y-3">
            {result.evidence_chain!.map((e, i) => (
              <li key={i} className="rounded-md bg-gray-50 p-3 text-sm space-y-1">
                {e.source && <p className="text-xs font-medium text-gray-500">{e.source}</p>}
                {e.finding && <p className="text-gray-700">{e.finding}</p>}
                {e.conclusion && <p className="text-gray-500 text-xs">{e.conclusion}</p>}
              </li>
            ))}
          </ul>
        </Accordion>
      )}
    </div>
  )
}

function SubmissionCard({ summary }: { summary: SubmissionSummary }) {
  const form = summary.form
  return (
    <Accordion title="提交表单摘要（本机缓存）">
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
        {[
          ['报销单号', form.case_id],
          ['申请人', form.applicant_name],
          ['部门', form.department],
          ['费用类型', form.expense_type],
          ['金额', formatAmount(form.total_amount, form.currency)],
          ['提交时间', formatDate(summary.submitted_at)],
        ].map(([label, value]) => (
          <div key={label}>
            <p className="text-xs text-gray-400">{label}</p>
            <p className="text-gray-800 font-medium">{value || '—'}</p>
          </div>
        ))}
      </div>
    </Accordion>
  )
}

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [task, setTask] = useState<AuditTask | null>(null)
  const [result, setResult] = useState<AuditResult | null>(null)
  const [summary, setSummary] = useState<SubmissionSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const resultFetchedRef = useRef(false)

  function stopPolling() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }

  function startPolling() {
    stopPolling()
    intervalRef.current = setInterval(fetchTask, POLL_INTERVAL)
  }

  async function handleRetry() {
    if (!id || retrying) return
    setRetrying(true)
    setError(null)
    try {
      const t = await retryTask(id)
      setTask(t)
      setResult(null)
      resultFetchedRef.current = false
      startPolling()
    } catch (e) {
      setError(e instanceof Error ? e.message : '重新审核失败')
    } finally {
      setRetrying(false)
    }
  }

  async function handleDelete() {
    if (!id || deleting) return
    if (!window.confirm('确定删除该审核任务？此操作不可恢复。')) return
    setDeleting(true)
    setError(null)
    try {
      await deleteTask(id)
      navigate('/')
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
      setDeleting(false)
    }
  }

  async function fetchResult(requestId: string) {
    if (resultFetchedRef.current) return
    resultFetchedRef.current = true
    try {
      const r = await getTaskResult(requestId)
      setResult(r)
    } catch {
      // non-fatal: result not yet available
    }
  }

  async function fetchTask() {
    if (!id) return
    try {
      const t = await getTask(id)
      setTask(t)
      if (t.status === 'completed') {
        stopPolling()
        fetchResult(t.request_id)
      } else if (t.status === 'failed') {
        stopPolling()
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
      stopPolling()
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!id) return
    setSummary(getSubmissionSummary(id))
    fetchTask()
    startPolling()
    return stopPolling
  }, [id])

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  if (error || !task) {
    return (
      <div className="max-w-3xl mx-auto rounded-xl border border-red-200 bg-red-50 p-6">
        <p className="text-sm font-semibold text-red-800">加载失败</p>
        <p className="text-xs text-red-600 mt-1">{error ?? '未找到任务'}</p>
        <Link to="/" className="mt-4 inline-block text-sm text-red-700 underline">返回列表</Link>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-gray-400 mb-1">任务详情</p>
          <h1 className="text-base font-semibold text-gray-900 font-mono break-all">
            {task.request_id}
          </h1>
          {task.claim_id && (
            <p className="text-xs text-gray-500 mt-0.5">报销单号：{task.claim_id}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 shrink-0">
          <CopyButton text={task.request_id} />
          <button
            type="button"
            onClick={handleRetry}
            disabled={retrying || task.status === 'running'}
            className="inline-flex items-center rounded-md border border-blue-300 bg-white px-3 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-50 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
          >
            {retrying ? '重新审核中…' : '重新审核'}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting || task.status === 'running'}
            className="inline-flex items-center rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleting ? '删除中…' : '删除'}
          </button>
          <Link to="/" className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-800 transition-colors">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            返回列表
          </Link>
        </div>
      </div>

      {/* Status banner (running / accepted / failed) */}
      <StatusBanner task={task} />

      {/* Result cards */}
      {result && (
        <>
          <ConclusionCard result={result} />
          {result.risk_dimensions && result.risk_dimensions.length > 0 && (
            <RiskDimensionCard dimensions={result.risk_dimensions} />
          )}
          <EvidenceCard result={result} />
        </>
      )}

      {/* Submission summary from localStorage */}
      {summary && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <SubmissionCard summary={summary} />
        </div>
      )}

      {/* Metadata */}
      <div className="rounded-xl border border-gray-100 bg-gray-50 px-5 py-4">
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs">
          {[
            ['提交时间', formatDate(task.submitted_at)],
            ['开始时间', formatDate(task.started_at)],
            ['完成时间', formatDate(task.finished_at)],
            ['更新时间', formatDate(task.updated_at)],
          ].map(([label, value]) => (
            <div key={label}>
              <span className="text-gray-400">{label}：</span>
              <span className="text-gray-600">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
