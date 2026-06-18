import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { FileText, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { deleteTask, listTasks, retryTask } from './api'
import { formatDate, truncateId } from './format'
import { formatAmount } from './lib/reimbursement-labels'
import {
  clearSubmissionSummaries,
  readSubmissionSummaries,
} from './lib/submission-summary'
import { TaskStatusBadge } from './status-badge'
import type { AuditTask } from './types'

const LIMIT = 20

const statusTabs = [
  { value: 'all', label: '全部' },
  { value: 'accepted', label: '已接收' },
  { value: 'running', label: '审核中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
]

function TaskStats({ tasks }: { tasks: AuditTask[] }) {
  const stats = useMemo(() => {
    const total = tasks.length
    const active = tasks.filter((task) => task.status === 'accepted' || task.status === 'running').length
    const completed = tasks.filter((task) => task.status === 'completed').length
    const failed = tasks.filter((task) => task.status === 'failed').length
    const completionRate = total > 0 ? Math.round((completed / total) * 100) : 0
    return { total, active, completed, failed, completionRate }
  }, [tasks])

  return (
    <div className='grid gap-3 md:grid-cols-4'>
      <Card>
        <CardHeader className='pb-2'>
          <CardDescription>当前页任务</CardDescription>
          <CardTitle className='text-2xl'>{stats.total}</CardTitle>
        </CardHeader>
      </Card>
      <Card>
        <CardHeader className='pb-2'>
          <CardDescription>待处理</CardDescription>
          <CardTitle className='text-2xl text-amber-600'>{stats.active}</CardTitle>
        </CardHeader>
      </Card>
      <Card>
        <CardHeader className='pb-2'>
          <CardDescription>已完成</CardDescription>
          <CardTitle className='text-2xl text-emerald-600'>{stats.completed}</CardTitle>
        </CardHeader>
      </Card>
      <Card>
        <CardHeader className='pb-2'>
          <CardDescription>完成率 / 失败</CardDescription>
          <CardTitle className='text-2xl'>
            {stats.completionRate}% / {stats.failed}
          </CardTitle>
        </CardHeader>
      </Card>
    </div>
  )
}

export function AuditTasksPage() {
  const [status, setStatus] = useState('all')
  const [offset, setOffset] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionId, setActionId] = useState<string | null>(null)
  const summaries = readSubmissionSummaries()

  const tasksQuery = useQuery({
    queryKey: ['audit-tasks', status, offset],
    queryFn: () =>
      listTasks({
        status: status === 'all' ? undefined : status,
        limit: LIMIT,
        offset,
      }),
  })

  const rows = useMemo(
    () =>
      (tasksQuery.data ?? []).map((task) => ({
        task,
        summary: summaries[task.request_id],
      })),
    [summaries, tasksQuery.data]
  )

  async function runAction(id: string, kind: 'retry' | 'delete') {
    setActionId(id)
    setNotice(null)
    try {
      if (kind === 'retry') {
        await retryTask(id)
        setNotice('已触发重新审核')
      } else {
        await deleteTask(id)
        setNotice('已删除任务')
      }
      await tasksQuery.refetch()
    } finally {
      setActionId(null)
    }
  }

  return (
    <>
      <Header fixed />
      <Main constrained className='space-y-5'>
        <div className='flex flex-col gap-3 md:flex-row md:items-end md:justify-between'>
          <div>
            <h1 className='text-2xl font-semibold tracking-tight'>审核工作台</h1>
            <p className='text-sm text-muted-foreground'>
              管理报销审核任务、跟踪状态，并查看自动审核结论。
            </p>
          </div>
          <Button asChild>
            <Link to='/audit/submit'>
              <Plus className='size-4' />
              新建报销
            </Link>
          </Button>
        </div>

        <TaskStats tasks={tasksQuery.data ?? []} />

        <Card>
          <CardHeader className='gap-3 md:flex-row md:items-center md:justify-between'>
            <div>
              <CardTitle>任务列表</CardTitle>
              <CardDescription>本机提交过的任务会叠加本地业务摘要。</CardDescription>
            </div>
            <div className='flex flex-wrap gap-2'>
              <Button variant='outline' size='sm' onClick={() => tasksQuery.refetch()}>
                <RotateCcw className='size-4' />
                刷新
              </Button>
              <Button
                variant='outline'
                size='sm'
                onClick={() => {
                  clearSubmissionSummaries()
                  setNotice('已清空本机提交摘要')
                }}
              >
                清空摘要
              </Button>
            </div>
          </CardHeader>
          <CardContent className='space-y-4'>
            <Tabs
              value={status}
              onValueChange={(value) => {
                setStatus(value)
                setOffset(0)
              }}
            >
              <TabsList className='overflow-x-auto'>
                {statusTabs.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value}>
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            {notice ? (
              <Alert>
                <AlertDescription>{notice}</AlertDescription>
              </Alert>
            ) : null}
            {tasksQuery.error ? (
              <Alert variant='destructive'>
                <AlertDescription>
                  {tasksQuery.error instanceof Error ? tasksQuery.error.message : '加载失败'}
                </AlertDescription>
              </Alert>
            ) : null}

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>单号 / 请求 ID</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>金额概要</TableHead>
                  <TableHead>提交时间</TableHead>
                  <TableHead className='text-right'>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasksQuery.isLoading ? (
                  Array.from({ length: 5 }).map((_, index) => (
                    <TableRow key={index}>
                      <TableCell colSpan={5}>
                        <div className='h-8 animate-pulse rounded-md bg-muted' />
                      </TableCell>
                    </TableRow>
                  ))
                ) : rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className='h-28 text-center text-muted-foreground'>
                      暂无任务，可新建报销申请。
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map(({ task, summary }) => (
                    <TableRow key={task.request_id}>
                      <TableCell>
                        <div className='flex min-w-0 items-center gap-3'>
                          <div className='rounded-md border bg-muted/40 p-2'>
                            <FileText className='size-4 text-muted-foreground' />
                          </div>
                          <div className='min-w-0'>
                            <div className='font-medium'>{summary?.form.case_id ?? task.claim_id ?? '-'}</div>
                            <div className='font-mono text-xs text-muted-foreground'>
                              {truncateId(task.request_id)}
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <TaskStatusBadge status={task.status} />
                      </TableCell>
                      <TableCell>
                        {summary ? formatAmount(summary.form.total_amount, summary.form.currency) : '-'}
                      </TableCell>
                      <TableCell>{formatDate(task.submitted_at)}</TableCell>
                      <TableCell>
                        <div className='flex justify-end gap-2'>
                          <Button variant='ghost' size='sm' asChild>
                            <Link to='/audit/tasks/$taskId' params={{ taskId: task.request_id }}>
                              详情
                            </Link>
                          </Button>
                          {task.status === 'failed' ? (
                            <Button
                              variant='outline'
                              size='sm'
                              disabled={actionId === task.request_id}
                              onClick={() => runAction(task.request_id, 'retry')}
                            >
                              重审
                            </Button>
                          ) : null}
                          <Button
                            variant='ghost'
                            size='icon'
                            disabled={actionId === task.request_id}
                            onClick={() => runAction(task.request_id, 'delete')}
                            aria-label='删除任务'
                          >
                            <Trash2 className='size-4' />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>

            <div className='flex items-center justify-between'>
              <Button
                variant='outline'
                size='sm'
                disabled={offset === 0}
                onClick={() => setOffset((value) => Math.max(0, value - LIMIT))}
              >
                上一页
              </Button>
              <span className='text-sm text-muted-foreground'>Offset {offset}</span>
              <Button
                variant='outline'
                size='sm'
                disabled={(tasksQuery.data?.length ?? 0) < LIMIT}
                onClick={() => setOffset((value) => value + LIMIT)}
              >
                下一页
              </Button>
            </div>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
