import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Copy, RotateCcw } from 'lucide-react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { getTask, getTaskResult, retryTask } from './api'
import {
  formatDate,
  normalizeRiskDimensions,
  toDisplayText,
} from './format'
import { getSubmissionSummary } from './lib/submission-summary'
import { TaskStatusBadge, VerdictBadge } from './status-badge'
import type { AuditResult, AuditTask } from './types'

function RiskScore({ score }: { score?: number }) {
  if (score == null) return null
  const pct = Math.max(0, Math.min(100, score))
  const tone = pct >= 70 ? 'bg-destructive' : pct >= 40 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div className='space-y-2'>
      <div className='flex items-center justify-between text-sm'>
        <span className='text-muted-foreground'>风险评分</span>
        <span className='font-semibold'>{pct}</span>
      </div>
      <div className='h-2 overflow-hidden rounded-full bg-muted'>
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function StatusBanner({ task }: { task: AuditTask }) {
  if (task.status === 'running') {
    return (
      <Alert>
        <RotateCcw className='size-4 animate-spin' />
        <AlertTitle>审核运行中</AlertTitle>
        <AlertDescription>{task.progress_message || '审核服务正在处理材料。'}</AlertDescription>
      </Alert>
    )
  }

  if (task.status === 'failed') {
    return (
      <Alert variant='destructive'>
        <AlertTitle>审核失败</AlertTitle>
        <AlertDescription>{task.error_detail || '任务执行失败，请稍后重试。'}</AlertDescription>
      </Alert>
    )
  }

  if (task.status === 'accepted') {
    return (
      <Alert>
        <AlertTitle>等待处理</AlertTitle>
        <AlertDescription>任务已接收，正在等待审核服务调度。</AlertDescription>
      </Alert>
    )
  }

  return null
}

function ResultCards({ result }: { result: AuditResult }) {
  const dimensions = normalizeRiskDimensions(result.risk_dimensions)
  return (
    <div className='grid gap-4 lg:grid-cols-[1.1fr_0.9fr]'>
      <Card>
        <CardHeader className='gap-3 md:flex-row md:items-start md:justify-between'>
          <div>
            <CardDescription>审核结论</CardDescription>
            <CardTitle className='text-xl leading-relaxed'>
              {result.conclusion ?? result.explanation ?? '未出结论'}
            </CardTitle>
          </div>
          <VerdictBadge verdict={result.verdict} />
        </CardHeader>
        <CardContent className='space-y-4'>
          {result.explanation ? (
            <p className='text-sm leading-6 text-muted-foreground'>{result.explanation}</p>
          ) : null}
          <RiskScore score={result.risk_score} />
          {result.manual_review_reason ? (
            <Alert>
              <AlertTitle>人工复核原因</AlertTitle>
              <AlertDescription>{result.manual_review_reason}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>风险维度</CardTitle>
          <CardDescription>按 0-10 量纲展示模型返回的分项风险。</CardDescription>
        </CardHeader>
        <CardContent className='space-y-3'>
          {dimensions.length === 0 ? (
            <div className='text-sm text-muted-foreground'>暂无风险维度。</div>
          ) : (
            dimensions.map((dimension) => (
              <div key={dimension.name} className='space-y-1'>
                <div className='flex justify-between text-sm'>
                  <span>{dimension.name}</span>
                  <span className='font-medium'>{dimension.score}/10</span>
                </div>
                <div className='h-2 overflow-hidden rounded-full bg-muted'>
                  <div className='h-full bg-primary' style={{ width: `${dimension.score * 10}%` }} />
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function EvidenceCards({ result }: { result: AuditResult }) {
  const reasons = result.reasons ?? []
  const refs = result.policy_refs ?? []
  const evidence = result.evidence_chain ?? []
  if (reasons.length === 0 && refs.length === 0 && evidence.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>证据与依据</CardTitle>
        <CardDescription>保留本地制度引用、审核理由和证据链。</CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        {reasons.length > 0 ? (
          <details open className='rounded-md border p-4'>
            <summary className='cursor-pointer font-medium'>审核理由（{reasons.length}）</summary>
            <ul className='mt-3 space-y-2 text-sm text-muted-foreground'>
              {reasons.map((reason, index) => (
                <li key={`${index}-${toDisplayText(reason)}`}>{toDisplayText(reason)}</li>
              ))}
            </ul>
          </details>
        ) : null}
        {refs.length > 0 ? (
          <details className='rounded-md border p-4'>
            <summary className='cursor-pointer font-medium'>策略引用（{refs.length}）</summary>
            <ul className='mt-3 space-y-2 font-mono text-xs text-muted-foreground'>
              {refs.map((ref, index) => (
                <li key={`${index}-${toDisplayText(ref)}`}>{toDisplayText(ref)}</li>
              ))}
            </ul>
          </details>
        ) : null}
        {evidence.length > 0 ? (
          <details className='rounded-md border p-4'>
            <summary className='cursor-pointer font-medium'>证据链（{evidence.length}）</summary>
            <div className='mt-3 space-y-3'>
              {evidence.map((item, index) => (
                <div key={index} className='rounded-md bg-muted/40 p-3 text-sm'>
                  {item.source ? <div className='font-medium'>{item.source}</div> : null}
                  {item.finding ? <div className='mt-1 text-muted-foreground'>{item.finding}</div> : null}
                  {item.conclusion ? <div className='mt-1 text-xs text-muted-foreground'>{item.conclusion}</div> : null}
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </CardContent>
    </Card>
  )
}

export function AuditTaskDetailPage({ taskId }: { taskId: string }) {
  const [action, setAction] = useState<'retry' | null>(null)
  const summary = getSubmissionSummary(taskId)

  const taskQuery = useQuery({
    queryKey: ['audit-task', taskId],
    queryFn: () => getTask(taskId),
    refetchInterval:
      taskId && taskId.length > 0 && taskId !== '-' ? (query) => {
        const task = query.state.data
        return task?.status === 'completed' || task?.status === 'failed' ? false : 3000
      } : false,
  })

  const resultQuery = useQuery({
    queryKey: ['audit-task-result', taskId],
    queryFn: () => getTaskResult(taskId),
    enabled: taskQuery.data?.status === 'completed',
  })

  /** C④: copy full (untruncated) task id to clipboard */
  async function copyFullId() {
    await navigator.clipboard.writeText(taskId)
  }

  /** C②: "重新审核" stays in the detail card; "删除任务" is removed */
  async function runRetry() {
    setAction('retry')
    try {
      await retryTask(taskId)
      await taskQuery.refetch()
    } finally {
      setAction(null)
    }
  }

  return (
    <>
      <Header fixed />
      <Main constrained className='space-y-5'>
        {/* C②: 移除"复制id""返回列表"按钮 — 只保留标题区 */}
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>任务详情</h1>
          {/* C④: 完整显示任务 ID（不截断），其后跟小复制 icon */}
          <div className='flex items-center gap-1.5'>
            <span className='break-all font-mono text-sm text-muted-foreground'>
              {taskId}
            </span>
            <Button
              type='button'
              variant='ghost'
              size='icon'
              className='size-6 shrink-0'
              aria-label='复制任务 ID'
              onClick={copyFullId}
            >
              <Copy className='size-3.5' />
            </Button>
          </div>
        </div>

        {taskQuery.error ? (
          <Alert variant='destructive'>
            <AlertTitle>任务加载失败</AlertTitle>
            <AlertDescription>
              {taskQuery.error instanceof Error ? taskQuery.error.message : '加载失败'}
            </AlertDescription>
          </Alert>
        ) : null}

        {taskQuery.data ? (
          <>
            <Card>
              <CardHeader className='gap-3 md:flex-row md:items-start md:justify-between'>
                <div>
                  <CardDescription>任务状态</CardDescription>
                  <CardTitle>{summary?.form.case_id ?? taskQuery.data.claim_id ?? taskId}</CardTitle>
                </div>
                <TaskStatusBadge status={taskQuery.data.status} />
              </CardHeader>
              <CardContent className='space-y-4'>
                <StatusBanner task={taskQuery.data} />
                <div className='grid gap-3 text-sm md:grid-cols-4'>
                  <div>
                    <div className='text-muted-foreground'>提交</div>
                    <div>{formatDate(taskQuery.data.submitted_at)}</div>
                  </div>
                  <div>
                    <div className='text-muted-foreground'>开始</div>
                    <div>{formatDate(taskQuery.data.started_at)}</div>
                  </div>
                  <div>
                    <div className='text-muted-foreground'>完成</div>
                    <div>{formatDate(taskQuery.data.finished_at)}</div>
                  </div>
                  <div>
                    <div className='text-muted-foreground'>更新</div>
                    <div>{formatDate(taskQuery.data.updated_at)}</div>
                  </div>
                </div>
                {/* C②: "重新审核"挪进详情卡；"删除任务"已移除 */}
                <div className='flex flex-wrap gap-2'>
                  <Button
                    variant='outline'
                    disabled={action === 'retry'}
                    onClick={runRetry}
                  >
                    <RotateCcw className='size-4' />
                    重新审核
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* C③: 移除"提交摘要"区块 */}
            {resultQuery.data ? <ResultCards result={resultQuery.data} /> : null}
            {resultQuery.data ? <EvidenceCards result={resultQuery.data} /> : null}
          </>
        ) : taskQuery.isLoading ? (
          <Card>
            <CardContent className='py-12 text-center text-muted-foreground'>正在加载任务...</CardContent>
          </Card>
        ) : null}
      </Main>
    </>
  )
}
