import { startTransition, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { Database, RefreshCw, Server, ShieldCheck } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
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
import { cn } from '@/lib/utils'
import type { ApiResult } from '@/types/api'
import { fetchCacheDetail, fetchCacheStats } from './api'
import {
  buildCacheOverview,
  parseHitRate,
  type CacheStat,
} from './model'

function getErrorMessage(error: unknown, fallback: string) {
  return (
    (error as AxiosError<ApiResult<unknown>>)?.response?.data?.message ?? fallback
  )
}

function getHitRateVariant(hitRate: number): 'default' | 'secondary' | 'destructive' {
  if (hitRate >= 85) return 'default'
  if (hitRate >= 60) return 'secondary'
  return 'destructive'
}

function OverviewCard({
  title,
  value,
  description,
  icon: Icon,
}: {
  title: string
  value: string | number
  description: string
  icon: typeof Database
}) {
  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
        <CardTitle className='text-sm font-medium'>{title}</CardTitle>
        <Icon className='size-4 text-muted-foreground' />
      </CardHeader>
      <CardContent className='space-y-1'>
        <div className='text-2xl font-semibold tracking-tight'>{value}</div>
        <p className='text-xs text-muted-foreground'>{description}</p>
      </CardContent>
    </Card>
  )
}

function buildChartData(stats: CacheStat[]) {
  return [...stats]
    .sort((left, right) => right.hitCount - left.hitCount)
    .slice(0, 6)
    .map((stat) => ({
      name: stat.name.length > 12 ? `${stat.name.slice(0, 12)}...` : stat.name,
      hitRate: parseHitRate(stat.hitRate),
    }))
}

export function CacheMonitorPage() {
  const [activeCacheName, setActiveCacheName] = useState('')

  const cacheListQuery = useQuery({
    queryKey: ['monitor', 'cache', 'list'],
    queryFn: fetchCacheStats,
  })

  const stats = cacheListQuery.data ?? []
  const currentCacheName =
    activeCacheName && stats.some((item) => item.name === activeCacheName)
      ? activeCacheName
      : (stats[0]?.name ?? '')

  const cacheDetailQuery = useQuery({
    queryKey: ['monitor', 'cache', 'detail', currentCacheName],
    queryFn: () => fetchCacheDetail(currentCacheName),
    enabled: currentCacheName.length > 0,
  })

  const overview = buildCacheOverview(stats)
  const chartData = buildChartData(stats)
  const activeDetail = cacheDetailQuery.data

  return (
    <>
      <Header fixed>
        <div className='flex items-center space-x-4'>
          <Search />
          <ProfileDropdown />
        </div>
      </Header>

      <Main className='flex flex-1 flex-col gap-4 sm:gap-6'>
        <div className='flex flex-wrap items-end justify-between gap-3'>
          <div className='space-y-1'>
            <h2 className='text-2xl font-bold tracking-tight'>缓存监控</h2>
            <p className='text-sm text-muted-foreground'>
              聚合展示多级缓存的条目规模、命中情况与单缓存明细。
            </p>
          </div>
          <Button
            type='button'
            variant='outline'
            size='sm'
            onClick={() => {
              cacheListQuery.refetch()
              if (activeCacheName) {
                cacheDetailQuery.refetch()
              }
            }}
            disabled={cacheListQuery.isFetching || cacheDetailQuery.isFetching}
          >
            <RefreshCw
              className={
                cacheListQuery.isFetching || cacheDetailQuery.isFetching
                  ? 'animate-spin'
                  : undefined
              }
            />
            刷新数据
          </Button>
        </div>

        <Alert>
          <Server />
          <AlertTitle>当前节点缓存视图</AlertTitle>
          <AlertDescription>
            本页展示的是当前应用实例内可见的缓存统计，命中率越高表示热点数据复用越充分。
          </AlertDescription>
        </Alert>

        {cacheListQuery.error ? (
          <Alert variant='destructive'>
            <AlertTitle>缓存统计加载失败</AlertTitle>
            <AlertDescription>
              {getErrorMessage(cacheListQuery.error, '请稍后重试')}
            </AlertDescription>
          </Alert>
        ) : null}

        <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
          <OverviewCard
            title='缓存区域'
            value={overview.cacheCount}
            description='当前暴露统计的缓存名称数量'
            icon={Database}
          />
          <OverviewCard
            title='缓存条目'
            value={overview.totalEntries}
            description='本地缓存估算条目总量'
            icon={ShieldCheck}
          />
          <OverviewCard
            title='命中次数'
            value={overview.totalHits}
            description='累计命中次数总和'
            icon={Database}
          />
          <OverviewCard
            title='平均命中率'
            value={`${overview.averageHitRate}%`}
            description='按缓存区域平均计算'
            icon={Server}
          />
        </div>

        <div className='grid gap-4 xl:grid-cols-[1.4fr_1fr]'>
          <Card>
            <CardHeader className='border-b pb-4'>
              <CardTitle>命中率分布</CardTitle>
              <CardDescription>
                取命中次数最高的 6 个缓存区域进行对比，帮助快速定位低命中对象。
              </CardDescription>
            </CardHeader>
            <CardContent className='pt-6'>
              {chartData.length === 0 ? (
                <div className='flex h-[260px] items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground'>
                  暂无缓存图表数据
                </div>
              ) : (
                <div className='h-[260px] text-primary'>
                  <ResponsiveContainer width='100%' height='100%'>
                    <BarChart data={chartData}>
                      <CartesianGrid strokeDasharray='3 3' vertical={false} />
                      <XAxis
                        dataKey='name'
                        tickLine={false}
                        axisLine={false}
                        fontSize={12}
                      />
                      <YAxis
                        tickLine={false}
                        axisLine={false}
                        fontSize={12}
                        domain={[0, 100]}
                      />
                      <ChartTooltip formatter={(value) => `${value}%`} />
                      <Bar dataKey='hitRate' fill='currentColor' radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className='border-b pb-4'>
              <CardTitle>当前选中缓存</CardTitle>
              <CardDescription>
                查看命中、淘汰与加载明细，判断缓存策略是否需要微调。
              </CardDescription>
            </CardHeader>
            <CardContent className='grid gap-4 pt-6 sm:grid-cols-2'>
              <div className='rounded-lg border bg-muted/20 p-4'>
                <div className='text-sm text-muted-foreground'>缓存名称</div>
                <div className='mt-1 break-all font-medium'>
                  {activeDetail?.name || currentCacheName || '-'}
                </div>
              </div>
              <div className='rounded-lg border bg-muted/20 p-4'>
                <div className='text-sm text-muted-foreground'>命中率</div>
                <div className='mt-1 text-xl font-semibold'>
                  {activeDetail?.hitRate || '-'}
                </div>
              </div>
              <div className='rounded-lg border bg-muted/20 p-4'>
                <div className='text-sm text-muted-foreground'>命中次数</div>
                <div className='mt-1 text-xl font-semibold'>
                  {activeDetail?.hitCount ?? 0}
                </div>
              </div>
              <div className='rounded-lg border bg-muted/20 p-4'>
                <div className='text-sm text-muted-foreground'>未命中次数</div>
                <div className='mt-1 text-xl font-semibold'>
                  {activeDetail?.missCount ?? 0}
                </div>
              </div>
              <div className='rounded-lg border bg-muted/20 p-4'>
                <div className='text-sm text-muted-foreground'>淘汰次数</div>
                <div className='mt-1 text-xl font-semibold'>
                  {activeDetail?.evictionCount ?? 0}
                </div>
              </div>
              <div className='rounded-lg border bg-muted/20 p-4'>
                <div className='text-sm text-muted-foreground'>加载次数</div>
                <div className='mt-1 text-xl font-semibold'>
                  {activeDetail?.loadCount ?? 0}
                </div>
              </div>
              <div className='rounded-lg border bg-muted/20 p-4 sm:col-span-2'>
                <div className='text-sm text-muted-foreground'>估算条目数</div>
                <div className='mt-1 text-xl font-semibold'>
                  {activeDetail?.size ?? 0}
                </div>
              </div>
              {cacheDetailQuery.error ? (
                <Alert variant='destructive' className='sm:col-span-2'>
                  <AlertTitle>缓存详情加载失败</AlertTitle>
                  <AlertDescription>
                    {getErrorMessage(cacheDetailQuery.error, '请稍后重试')}
                  </AlertDescription>
                </Alert>
              ) : null}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className='border-b pb-4'>
            <CardTitle>缓存列表</CardTitle>
            <CardDescription>
              点击任一缓存可联动查看详情，低命中率缓存会以醒目状态提示。
            </CardDescription>
          </CardHeader>
          <CardContent className='pt-6'>
            <div className='rounded-md border'>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>缓存名称</TableHead>
                    <TableHead className='w-28'>条目数</TableHead>
                    <TableHead className='w-28'>命中</TableHead>
                    <TableHead className='w-28'>未命中</TableHead>
                    <TableHead className='w-28'>命中率</TableHead>
                    <TableHead className='w-20 text-right'>操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cacheListQuery.isLoading ? (
                    <TableRow>
                      <TableCell colSpan={6} className='text-center text-sm text-muted-foreground'>
                        缓存统计加载中...
                      </TableCell>
                    </TableRow>
                  ) : stats.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className='text-center text-sm text-muted-foreground'>
                        暂无缓存统计
                      </TableCell>
                    </TableRow>
                  ) : (
                    stats.map((stat) => {
                      const hitRate = parseHitRate(stat.hitRate)
                      const isActive = stat.name === currentCacheName
                      return (
                        <TableRow
                          key={stat.name}
                          className={cn(isActive && 'bg-muted/40')}
                        >
                          <TableCell>
                            <button
                              type='button'
                              className='text-left font-medium hover:text-primary'
                              onClick={() => {
                                startTransition(() => {
                                  setActiveCacheName(stat.name)
                                })
                              }}
                            >
                              {stat.name}
                            </button>
                          </TableCell>
                          <TableCell>{stat.size}</TableCell>
                          <TableCell>{stat.hitCount}</TableCell>
                          <TableCell>{stat.missCount}</TableCell>
                          <TableCell>
                            <Badge variant={getHitRateVariant(hitRate)}>
                              {stat.hitRate || '0.00%'}
                            </Badge>
                          </TableCell>
                          <TableCell className='text-right'>
                            <Button
                              type='button'
                              size='sm'
                              variant='ghost'
                              onClick={() => {
                                startTransition(() => {
                                  setActiveCacheName(stat.name)
                                })
                              }}
                            >
                              查看
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
