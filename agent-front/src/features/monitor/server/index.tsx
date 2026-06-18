import { useQuery } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import { Activity, Database, HardDrive, RefreshCw, Server } from 'lucide-react'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { ApiResult } from '@/types/api'
import { fetchServerInfo } from './api'
import { buildServerOverview, toUsageChartData } from './model'

function getErrorMessage(error: unknown, fallback: string) {
  return (
    (error as AxiosError<ApiResult<unknown>>)?.response?.data?.message ?? fallback
  )
}

function getUsageVariant(usage: number): 'default' | 'secondary' | 'destructive' {
  if (usage >= 80) return 'destructive'
  if (usage >= 50) return 'secondary'
  return 'default'
}

function renderUsageBar(usage: number) {
  const safeUsage = Math.max(0, Math.min(usage, 100))

  return (
    <div className='space-y-2'>
      <div className='flex items-center justify-between text-xs text-muted-foreground'>
        <span>使用率</span>
        <span>{safeUsage}%</span>
      </div>
      <div className='h-2 rounded-full bg-muted'>
        <div
          className='h-2 rounded-full bg-primary transition-all'
          style={{ width: `${safeUsage}%` }}
        />
      </div>
    </div>
  )
}

function OverviewCard({
  title,
  value,
  description,
  icon: Icon,
  usage,
}: {
  title: string
  value: string | number
  description: string
  icon: typeof Server
  usage?: number
}) {
  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
        <CardTitle className='text-sm font-medium'>{title}</CardTitle>
        <Icon className='size-4 text-muted-foreground' />
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='text-2xl font-semibold tracking-tight'>{value}</div>
        <p className='text-xs text-muted-foreground'>{description}</p>
        {typeof usage === 'number' ? renderUsageBar(usage) : null}
      </CardContent>
    </Card>
  )
}

function InfoField({ label, value }: { label: string; value: string }) {
  return (
    <div className='rounded-lg border bg-muted/20 p-4'>
      <div className='text-sm text-muted-foreground'>{label}</div>
      <div className='mt-1 break-all font-medium'>{value || '-'}</div>
    </div>
  )
}

export function ServerMonitorPage() {
  const serverQuery = useQuery({
    queryKey: ['monitor', 'server', 'info'],
    queryFn: fetchServerInfo,
  })

  const server = serverQuery.data
  const overview = server ? buildServerOverview(server) : null
  const usageChartData = server ? toUsageChartData(server) : []
  const diskRows = server ? [...server.sysFiles].sort((left, right) => right.usage - left.usage) : []

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
            <h2 className='text-2xl font-bold tracking-tight'>服务监控</h2>
            <p className='text-sm text-muted-foreground'>
              查看当前节点 CPU、内存、JVM、系统信息与磁盘使用情况。
            </p>
          </div>
          <Button
            type='button'
            variant='outline'
            size='sm'
            onClick={() => serverQuery.refetch()}
            disabled={serverQuery.isFetching}
          >
            <RefreshCw
              className={serverQuery.isFetching ? 'animate-spin' : undefined}
            />
            刷新数据
          </Button>
        </div>

        <Alert>
          <Server />
          <AlertTitle>实时采集当前实例指标</AlertTitle>
          <AlertDescription>
            服务监控数据由当前应用实例实时采集生成，适合快速排查资源占用与运行时状态。
          </AlertDescription>
        </Alert>

        {serverQuery.error ? (
          <Alert variant='destructive'>
            <AlertTitle>服务监控加载失败</AlertTitle>
            <AlertDescription>
              {getErrorMessage(serverQuery.error, '请稍后重试')}
            </AlertDescription>
          </Alert>
        ) : null}

        <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
          <OverviewCard
            title='CPU 使用率'
            value={overview ? `${overview.cpuUsage}%` : '-'}
            description='当前进程所在主机 CPU 总体使用情况'
            icon={Activity}
            usage={overview?.cpuUsage}
          />
          <OverviewCard
            title='系统内存'
            value={overview ? `${overview.memoryUsage}%` : '-'}
            description={server ? `已用 ${server.mem.used} / 总计 ${server.mem.total}` : '等待数据'}
            icon={Database}
            usage={overview?.memoryUsage}
          />
          <OverviewCard
            title='JVM 内存'
            value={overview ? `${overview.jvmUsage}%` : '-'}
            description={server ? `已用 ${server.jvm.used} / 最大 ${server.jvm.max}` : '等待数据'}
            icon={Server}
            usage={overview?.jvmUsage}
          />
          <OverviewCard
            title='磁盘分区'
            value={overview?.diskCount ?? '-'}
            description={overview ? `${overview.osName || '未知系统'} · 运行 ${overview.runtime || '-'}` : '等待数据'}
            icon={HardDrive}
          />
        </div>

        <Tabs defaultValue='overview' className='gap-4'>
          <TabsList>
            <TabsTrigger value='overview'>资源概览</TabsTrigger>
            <TabsTrigger value='jvm'>JVM 详情</TabsTrigger>
            <TabsTrigger value='disk'>磁盘信息</TabsTrigger>
          </TabsList>

          <TabsContent value='overview' className='space-y-4'>
            <div className='grid gap-4 xl:grid-cols-[1.2fr_1fr]'>
              <Card>
                <CardHeader className='border-b pb-4'>
                  <CardTitle>资源占用对比</CardTitle>
                  <CardDescription>
                    统一展示 CPU、系统内存与 JVM 内存使用率，便于横向比较。
                  </CardDescription>
                </CardHeader>
                <CardContent className='pt-6'>
                  {usageChartData.length === 0 ? (
                    <div className='flex h-[280px] items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground'>
                      服务资源数据加载中...
                    </div>
                  ) : (
                    <div className='h-[280px] text-primary'>
                      <ResponsiveContainer width='100%' height='100%'>
                        <BarChart data={usageChartData}>
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
                          <Bar dataKey='usage' fill='currentColor' radius={[6, 6, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className='border-b pb-4'>
                  <CardTitle>系统信息</CardTitle>
                  <CardDescription>
                    这里展示当前运行实例的主机、网络与工作目录信息。
                  </CardDescription>
                </CardHeader>
                <CardContent className='grid gap-4 pt-6 sm:grid-cols-2'>
                  <InfoField label='主机名' value={server?.sys.computerName ?? '-'} />
                  <InfoField label='主机 IP' value={server?.sys.computerIp ?? '-'} />
                  <InfoField label='操作系统' value={server?.sys.osName ?? '-'} />
                  <InfoField label='系统架构' value={server?.sys.osArch ?? '-'} />
                  <div className='sm:col-span-2'>
                    <InfoField label='项目路径' value={server?.sys.userDir ?? '-'} />
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value='jvm' className='space-y-4'>
            <div className='grid gap-4 xl:grid-cols-[1fr_1fr]'>
              <Card>
                <CardHeader className='border-b pb-4'>
                  <CardTitle>JVM 基础信息</CardTitle>
                  <CardDescription>
                    核心运行环境、启动时间与运行时长一并展示。
                  </CardDescription>
                </CardHeader>
                <CardContent className='grid gap-4 pt-6 sm:grid-cols-2'>
                  <InfoField label='JVM 名称' value={server?.jvm.name ?? '-'} />
                  <InfoField label='Java 版本' value={server?.jvm.version ?? '-'} />
                  <InfoField label='启动时间' value={server?.jvm.startTime ?? '-'} />
                  <InfoField label='运行时长' value={server?.jvm.runTime ?? '-'} />
                  <div className='sm:col-span-2'>
                    <InfoField label='JAVA_HOME' value={server?.jvm.home ?? '-'} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className='border-b pb-4'>
                  <CardTitle>JVM 内存详情</CardTitle>
                  <CardDescription>
                    展示当前已分配、最大可用与空闲内存，帮助判断堆空间余量。
                  </CardDescription>
                </CardHeader>
                <CardContent className='space-y-4 pt-6'>
                  <div className='flex items-center gap-2'>
                    <Badge variant={getUsageVariant(server?.jvm.usage ?? 0)}>
                      {server ? `${server.jvm.usage}%` : '-'}
                    </Badge>
                    <span className='text-sm text-muted-foreground'>当前 JVM 使用率</span>
                  </div>
                  {renderUsageBar(server?.jvm.usage ?? 0)}
                  <div className='grid gap-4 sm:grid-cols-2'>
                    <InfoField label='已分配堆内存' value={server?.jvm.total ?? '-'} />
                    <InfoField label='最大可用内存' value={server?.jvm.max ?? '-'} />
                    <InfoField label='已使用内存' value={server?.jvm.used ?? '-'} />
                    <InfoField label='空闲内存' value={server?.jvm.free ?? '-'} />
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value='disk'>
            <Card>
              <CardHeader className='border-b pb-4'>
                <CardTitle>磁盘使用情况</CardTitle>
                <CardDescription>
                  按使用率从高到低排序，帮助快速发现逼近阈值的挂载点。
                </CardDescription>
              </CardHeader>
              <CardContent className='pt-6'>
                <div className='rounded-md border'>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>盘符</TableHead>
                        <TableHead className='w-36'>类型</TableHead>
                        <TableHead className='w-32'>总量</TableHead>
                        <TableHead className='w-32'>已用</TableHead>
                        <TableHead className='w-32'>可用</TableHead>
                        <TableHead className='w-40'>使用率</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {serverQuery.isLoading ? (
                        <TableRow>
                          <TableCell colSpan={6} className='text-center text-sm text-muted-foreground'>
                            磁盘信息加载中...
                          </TableCell>
                        </TableRow>
                      ) : diskRows.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} className='text-center text-sm text-muted-foreground'>
                            暂无磁盘信息
                          </TableCell>
                        </TableRow>
                      ) : (
                        diskRows.map((disk) => (
                          <TableRow key={`${disk.dirName}-${disk.sysTypeName}`}>
                            <TableCell>
                              <div className='space-y-1'>
                                <div className='font-medium'>{disk.dirName || '-'}</div>
                                <div className='text-xs text-muted-foreground'>
                                  {disk.sysTypeName || '-'}
                                </div>
                              </div>
                            </TableCell>
                            <TableCell>{disk.typeName || '-'}</TableCell>
                            <TableCell>{disk.total || '-'}</TableCell>
                            <TableCell>{disk.used || '-'}</TableCell>
                            <TableCell>{disk.free || '-'}</TableCell>
                            <TableCell>
                              <div className='space-y-2'>
                                <Badge variant={getUsageVariant(disk.usage)}>
                                  {disk.usage}%
                                </Badge>
                                {renderUsageBar(disk.usage)}
                              </div>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}
