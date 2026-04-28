import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getTask, getTaskResult } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import {
  ATTACHMENT_CATEGORY_LABELS,
  SCENARIO_FLAG_LABELS,
  formatAmount,
  formatFileSize,
} from '../lib/reimbursementLabels'
import { getSubmissionSummary } from '../lib/submissionSummary'
import type { AuditTask, AuditResult, SubmissionSummary, Verdict } from '../types'

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

const RISK_DIMENSION_LABELS: Record<string, string> = {
  invoice: '发票',
  amount: '金额',
  approval: '审批',
  budget: '预算',
  anomaly: '异常',
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

function ResultBadge({ passed }: { passed: boolean }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
      passed ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
    }`}
    >
      {passed ? '自动审核通过' : '未自动通过'}
    </span>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className="text-sm text-gray-700 break-words">{value || '—'}</p>
    </div>
  )
}

function JsonPreview({ value }: { value: unknown }) {
  return (
    <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-600">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function SubmittedSummarySection({ summary }: { summary: SubmissionSummary | null }) {
  const [showPayload, setShowPayload] = useState(false)

  if (!summary) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-base font-semibold text-gray-800">提交表单摘要</h2>
        <p className="mt-2 text-sm text-gray-500">
          未命中本机 `localStorage` 摘要。后端任务详情仍可用，但历史任务或清理浏览器缓存后不会回显完整表单。
        </p>
      </div>
    )
  }

  const form = summary.form

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-800">提交表单摘要</h2>
          <p className="text-xs text-gray-500 mt-1">提交时间：{formatDate(summary.submitted_at)}</p>
        </div>
        <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm font-semibold text-blue-700">
          {formatAmount(form.total_amount, form.currency)}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <InfoItem label="报销单号" value={form.case_id} />
        <InfoItem label="申请人" value={`${form.applicant_name} / ${form.applicant_employee_id}`} />
        <InfoItem label="费用类型" value={form.expense_type} />
        <InfoItem label="部门" value={form.department} />
        <InfoItem label="成本中心" value={form.cost_center} />
        <InfoItem label="项目/客户" value={form.project_name || form.customer_name} />
        <InfoItem label="支付方式" value={form.payment_method} />
        <InfoItem label="审批状态" value={form.approval_status} />
      </div>

      <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
        <p className="text-xs font-medium text-gray-500 mb-2">报销事由</p>
        <p className="text-sm text-gray-800 leading-relaxed">{form.reimbursement_reason || '—'}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-800 mb-3">发票与金额</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoItem label="发票类型" value={form.invoice_type} />
            <InfoItem label="验真状态" value={form.invoice_validation_status} />
            <InfoItem label="发票号码" value={form.invoice_number} />
            <InfoItem label="开票日期" value={form.invoice_issue_date} />
            <InfoItem label="销售方" value={form.invoice_seller_name} />
            <InfoItem label="购买方抬头" value={form.invoice_buyer_title} />
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 p-4">
          <p className="text-sm font-medium text-gray-800 mb-3">
            {form.expense_type === '业务招待' ? '招待信息' : '行程/场景信息'}
          </p>
          {form.expense_type === '业务招待' ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <InfoItem label="招待对象" value={form.entertainment_target} />
              <InfoItem label="客户公司" value={form.entertainment_company} />
              <InfoItem label="参与人数" value={form.participant_count} />
              <InfoItem label="人均金额" value={formatAmount(form.per_capita_amount, form.currency)} />
              <InfoItem label="招待时段" value={form.entertainment_period} />
              <InfoItem label="业务目的" value={form.business_purpose} />
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <InfoItem label="出发城市" value={form.travel_from_city} />
              <InfoItem label="到达城市" value={form.travel_to_city} />
              <InfoItem label="出差日期" value={`${form.travel_start_date} 至 ${form.travel_end_date}`} />
              <InfoItem label="交通方式" value={form.transportation_type} />
              <InfoItem label="住宿晚数" value={form.hotel_nights} />
              <InfoItem label="事前申请" value={form.has_pre_trip_approval ? '是' : '否'} />
            </div>
          )}
        </div>
      </div>

      <div>
        <p className="text-sm font-medium text-gray-800 mb-2">异常场景</p>
        {form.scenario_flags.length === 0 ? (
          <p className="text-sm text-gray-500">未标记异常场景</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {form.scenario_flags.map(flag => (
              <span key={flag} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                {SCENARIO_FLAG_LABELS[flag]}
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <p className="text-sm font-medium text-gray-800 mb-2">附件摘要</p>
        {summary.attachments.length === 0 ? (
          <p className="text-sm text-gray-500">无附件摘要</p>
        ) : (
          <div className="space-y-2">
            {summary.attachments.map(item => (
              <div key={item.id} className="flex flex-col gap-1 rounded-lg border border-gray-100 bg-gray-50 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-gray-800">{item.name}</p>
                  <p className="text-xs text-gray-500">{ATTACHMENT_CATEGORY_LABELS[item.category]} · {item.type}</p>
                </div>
                <span className="text-xs text-gray-500">{formatFileSize(item.size)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <button
          onClick={() => setShowPayload(value => !value)}
          className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          {showPayload ? '收起提交 payload' : '查看提交 payload'}
        </button>
        {showPayload && (
          <pre className="mt-2 p-3 bg-gray-950 text-gray-100 border border-gray-200 rounded-md text-xs overflow-auto max-h-96">
            {JSON.stringify(form, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

function ResultSection({ result }: { result: AuditResult }) {
  const [showRaw, setShowRaw] = useState(false)
  const [showExtracted, setShowExtracted] = useState(false)
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

      <div className="grid gap-4 md:grid-cols-3">
        {typeof result.result === 'boolean' && (
          <div>
            <p className="text-sm text-gray-500 mb-1">自动判断</p>
            <ResultBadge passed={result.result} />
          </div>
        )}
        {result.conclusion && (
          <InfoItem label="中文结论" value={result.conclusion} />
        )}
        {result.reviewed_by && (
          <InfoItem label="审核来源" value={result.reviewed_by} />
        )}
      </div>

      {result.risk_score != null && (
        <div>
          <p className="text-sm text-gray-600 mb-1">风险评分</p>
          <RiskBar score={result.risk_score} />
        </div>
      )}

      {result.risk_dimensions && result.risk_dimensions.length > 0 && (
        <div>
          <p className="text-sm text-gray-500 mb-2">风险维度</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {result.risk_dimensions.map(item => (
              <div key={`${item.name}-${item.score}`} className="rounded-lg border border-gray-200 p-3">
                <p className="text-xs text-gray-500">{RISK_DIMENSION_LABELS[item.name] ?? item.name}</p>
                <p className="mt-1 text-lg font-semibold text-gray-800">{item.score}<span className="text-xs font-normal text-gray-400"> / 10</span></p>
              </div>
            ))}
          </div>
        </div>
      )}

      {result.claim_id && (
        <div>
          <p className="text-sm text-gray-500">案例 ID</p>
          <p className="text-sm text-gray-800 font-mono">{result.claim_id}</p>
        </div>
      )}

      {result.explanation && (
        <div>
          <p className="text-sm text-gray-500 mb-1">审核说明</p>
          <p className="text-sm text-gray-800 leading-relaxed">{result.explanation}</p>
        </div>
      )}

      {result.summary && !result.explanation && (
        <div>
          <p className="text-sm text-gray-500 mb-1">摘要</p>
          <p className="text-sm text-gray-800 leading-relaxed">{result.summary}</p>
        </div>
      )}

      {result.reasons && result.reasons.length > 0 && (
        <div>
          <p className="text-sm text-gray-500 mb-1">结论依据</p>
          <ul className="space-y-1">
            {result.reasons.map((reason, index) => (
              <li key={`${reason}-${index}`} className="text-sm text-gray-700 flex items-start gap-1.5">
                <span className="text-blue-400 mt-0.5">•</span>
                {reason}
              </li>
            ))}
          </ul>
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

      {result.evidence_chain && result.evidence_chain.length > 0 && (
        <div>
          <p className="text-sm text-gray-500 mb-2">证据链</p>
          <div className="space-y-2">
            {result.evidence_chain.map((item, index) => (
              <div key={`${item.source ?? 'evidence'}-${index}`} className="rounded-lg border border-gray-200 p-3">
                <p className="text-xs text-gray-400 mb-1">{item.source ?? `证据 ${index + 1}`}</p>
                <p className="text-sm text-gray-800">{item.finding ?? '—'}</p>
                {item.conclusion && (
                  <p className="mt-1 text-xs text-gray-500">结论：{item.conclusion}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {result.extracted_data && Object.keys(result.extracted_data).length > 0 && (
        <div>
          <button
            onClick={() => setShowExtracted(value => !value)}
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            {showExtracted ? '收起提取数据' : '查看提取数据'}
          </button>
          {showExtracted && <JsonPreview value={result.extracted_data} />}
        </div>
      )}

      {result.timestamp && (
        <InfoItem label="结果时间" value={result.timestamp} />
      )}

      <div>
        <button
          onClick={() => setShowRaw(value => !value)}
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
  const [summary, setSummary] = useState<SubmissionSummary | null>(null)
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
    setSummary(getSubmissionSummary(id))
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
    <div className="space-y-6">
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

        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <InfoItem label="案例 ID" value={task.claim_id ?? summary?.form.case_id ?? ''} />
          <InfoItem label="提交时间" value={formatDate(task.submitted_at)} />
          <InfoItem label="开始时间" value={formatDate(task.started_at)} />
          <InfoItem label="完成时间" value={formatDate(task.finished_at)} />
        </div>

        {task.status === 'failed' && task.error_detail && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-xs text-red-500 font-medium mb-1">错误详情</p>
            <p className="text-sm text-red-800">{task.error_detail}</p>
          </div>
        )}
      </div>

      <SubmittedSummarySection summary={summary} />

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
