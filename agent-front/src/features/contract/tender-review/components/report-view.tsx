import { ArrowLeft, Printer } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { TenderReviewMockData } from '../types'

type ReportViewProps = {
  data: TenderReviewMockData
  onBack: () => void
}

export function ReportView({ data, onBack }: ReportViewProps) {
  return (
    <div className='rounded-xl bg-muted/60 p-4 md:p-8'>
      <div className='mx-auto mb-4 flex max-w-[820px] items-center justify-between gap-3'>
        <div className='text-sm text-muted-foreground'>
          评标报告预览 · 可直接打印或导出 PDF
        </div>
        <div className='flex gap-2'>
          <Button type='button' variant='outline' size='sm' onClick={onBack}>
            <ArrowLeft className='size-4' />
            返回对比
          </Button>
          <Button type='button' size='sm' onClick={() => window.print()}>
            <Printer className='size-4' />
            导出 PDF
          </Button>
        </div>
      </div>

      <article className='mx-auto max-w-[820px] rounded-md bg-background px-8 py-10 shadow-xl md:px-16 md:py-14'>
        <header className='border-b-2 border-foreground pb-6 text-center'>
          <div className='text-sm font-semibold tracking-wide text-primary'>
            交易大脑 · 智能招投标审核
          </div>
          <h1 className='mt-3 text-2xl font-bold tracking-wide'>评 标 报 告</h1>
          <div className='mt-2 text-sm text-muted-foreground'>
            {data.projectInfo.name}
          </div>
        </header>

        <ReportMeta data={data} />
        <CompareNotice data={data} />
        <RankingSection data={data} />
        <DetailSection data={data} />
        <Conclusion data={data} />

        <footer className='mt-10 flex items-end justify-between border-t pt-6'>
          <div className='text-xs leading-6 text-muted-foreground'>
            交易大脑智能审核系统生成
            <br />
            报告编号：{data.projectInfo.reportNo}
          </div>
          <div className='text-center'>
            <div className='text-xs text-muted-foreground'>评标委员会（签章）</div>
            <div className='mt-8 h-px w-32 bg-foreground' />
            <div className='mt-2 text-xs text-muted-foreground'>
              {data.projectInfo.reviewDate}
            </div>
          </div>
        </footer>
      </article>
    </div>
  )
}

function ReportMeta({ data }: { data: TenderReviewMockData }) {
  const meta = [
    ['项目名称', data.projectInfo.name],
    ['招标编号', data.projectInfo.code],
    ['评标办法', `${data.projectInfo.method}（满分 100）`],
    ['投标人数量', `${data.reviewBidders.length} 家`],
    ['招标控制价', data.projectInfo.controlPrice],
    ['评标日期', data.projectInfo.reviewDate],
  ]

  return (
    <section className='mt-7 grid overflow-hidden rounded-lg border md:grid-cols-2'>
      {meta.map(([label, value], index) => (
        <div
          key={label}
          className={index % 2 === 0 ? 'bg-background p-4' : 'bg-muted/40 p-4'}
        >
          <div className='text-xs font-medium text-muted-foreground'>{label}</div>
          <div className='mt-1 text-sm font-semibold'>{value}</div>
        </div>
      ))}
    </section>
  )
}

function CompareNotice({ data }: { data: TenderReviewMockData }) {
  const notice = data.compareNotice
  if (!notice || (!notice.stale && !notice.provisional && notice.warnings.length === 0)) {
    return null
  }

  return (
    <Alert className='mt-6'>
      <AlertTitle>
        {notice.stale
          ? '横比结果已过期'
          : notice.provisional
            ? '暂定排名'
            : '横比告警'}
      </AlertTitle>
      <AlertDescription className='mt-2 space-y-1'>
        {notice.stale ? <div>投标人有变化，请重新横比后再展示推荐结论。</div> : null}
        {notice.provisional ? (
          <div>暂定排名，定标由招标人依法确定。</div>
        ) : null}
        {notice.warnings.map((warning) => (
          <div key={warning}>{warning}</div>
        ))}
      </AlertDescription>
    </Alert>
  )
}

function RankingSection({ data }: { data: TenderReviewMockData }) {
  const provisional = Boolean(data.compareNotice?.provisional)
  return (
    <section className='mt-8'>
      <ReportTitle>一、评标结论与排名</ReportTitle>
      <div className='mt-4 overflow-hidden rounded-lg border'>
        <div className='grid grid-cols-[48px_1fr_90px_1fr] border-b bg-muted/40 text-xs font-semibold text-muted-foreground'>
          <div className='p-3'>排名</div>
          <div className='p-3'>投标人</div>
          <div className='p-3 text-center'>综合得分</div>
          <div className='p-3'>评定结果</div>
        </div>
        {data.reviewBidders.map((bidder) => (
          <div
            key={bidder.id}
            className='grid grid-cols-[48px_1fr_90px_1fr] items-center border-b last:border-b-0'
          >
            <div className='p-3 text-sm font-bold'>{bidder.rank}</div>
            <div className='p-3 text-sm font-semibold'>{bidder.name}</div>
            <div className='p-3 text-center text-sm font-bold'>
              {bidder.total}
            </div>
            <div className='p-3 text-sm font-medium text-muted-foreground'>
              {getCandidateLabel(bidder.rank, provisional)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function DetailSection({ data }: { data: TenderReviewMockData }) {
  const winnerIndex = data.reviewBidders.findIndex((bidder) => bidder.rank === 1)
  const firstIndex = winnerIndex >= 0 ? winnerIndex : 0
  const rows = data.compareGroups.flatMap((group) =>
    group.rows.map((row) => ({
      group: group.name,
      name: row.name,
      max: row.max,
      got: row.cells[firstIndex] ?? 0,
    }))
  )

  return (
    <section className='mt-8'>
      <ReportTitle>二、第一中标候选人评分明细</ReportTitle>
      <div className='mt-2 text-sm text-muted-foreground'>
        {data.reviewBidders[0]?.name} · 综合得分 {data.reviewBidders[0]?.total} 分
      </div>
      {rows.length > 0 ? (
        <div className='mt-4 overflow-hidden rounded-lg border'>
          {rows.map((row, index) => (
          <div
            key={`${row.group}-${row.name}`}
            className={`grid grid-cols-[1fr_90px_90px] border-b last:border-b-0 ${
              index % 2 ? 'bg-muted/20' : ''
            }`}
          >
            <div className='p-3 text-sm'>
              <span className='text-xs text-muted-foreground'>{row.group}</span>
              <br />
              {row.name}
            </div>
            <div className='p-3 text-center text-sm text-muted-foreground'>
              {row.max}
            </div>
            <div className='p-3 text-center text-sm font-semibold'>{row.got}</div>
          </div>
          ))}
        </div>
      ) : (
        <div className='mt-4 rounded-lg border border-dashed p-4 text-sm text-muted-foreground'>
          暂无横比评分明细。
        </div>
      )}
    </section>
  )
}

function Conclusion({ data }: { data: TenderReviewMockData }) {
  const winner = data.reviewBidders[0]
  const notice = data.compareNotice
  const second = data.reviewBidders[1]
  const third = data.reviewBidders[2]
  return (
    <section className='mt-8'>
      <ReportTitle>三、评标委员会意见</ReportTitle>
      <p className='mt-4 text-sm leading-8 text-muted-foreground'>
        经评标委员会对 {data.reviewBidders.length}{' '}
        家投标人进行资格审查、技术评审与商务评审，
        <b className='text-foreground'>{winner?.name}</b>
        综合得分 {winner?.total ?? '-'} 分，位列第一。
        {notice?.provisional || !notice?.recommended ? (
          <>
            本次横比为
            <b className='text-amber-700'>暂定排名</b>
            ，定标由招标人依法确定。
          </>
        ) : (
          <>
            建议推荐为
            <b className='text-emerald-700'>第一中标候选人</b>。
          </>
        )}
        {notice?.explanation ? (
          <>
            <br />
            <br />
            {notice.explanation}
          </>
        ) : null}
        {notice?.warnings.length ? (
          <>
            <br />
            <br />
            需提请注意：{notice.warnings.join('；')}
          </>
        ) : null}
        {second ? (
          <>
            <br />
            <br />
            {second.name}（{second.total} 分）
            {third ? `、${third.name}（${third.total} 分）` : ''}
            依次列后。
          </>
        ) : null}
      </p>
    </section>
  )
}

function ReportTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className='flex items-center gap-2 text-lg font-bold'>
      <span className='h-5 w-1 rounded-full bg-primary' />
      {children}
    </h2>
  )
}

function getCandidateLabel(rank: number, provisional: boolean) {
  if (provisional) return rank > 0 ? `暂定第 ${rank} 名` : '暂定排名'
  if (rank === 1) return '第一中标候选人'
  if (rank === 2) return '第二中标候选人'
  if (rank === 3) return '第三中标候选人'
  return '—'
}
