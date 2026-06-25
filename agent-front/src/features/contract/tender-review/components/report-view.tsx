import { ArrowLeft, Printer } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type {
  TenderCompareScoreRow,
  TenderEligibilityCheck,
  TenderReviewMockData,
  TenderScoreEvidence,
  TenderScoreIssue,
  TenderScoringItem,
} from '../types'

type ReportViewProps = {
  data: TenderReviewMockData
  onBack: () => void
}

export function ReportView({ data, onBack }: ReportViewProps) {
  return (
    <div className='tender-report-shell rounded-xl bg-muted/60 p-4 md:p-8'>
      <div className='tender-report-actions mb-4 flex items-center justify-between gap-3'>
        <div className='text-sm text-muted-foreground'>
          评标报告预览 · 可直接打印或导出 PDF
        </div>
        <div className='flex gap-2'>
          <Button type='button' variant='outline' size='sm' onClick={onBack}>
            <ArrowLeft className='size-4' />
            返回详情
          </Button>
          <Button type='button' size='sm' onClick={() => window.print()}>
            <Printer className='size-4' />
            导出 PDF
          </Button>
        </div>
      </div>

      <article className='tender-report-paper rounded-md bg-background px-8 py-10 shadow-xl md:px-16 md:py-14'>
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
        <EligibilitySection data={data} />
        <PriceScoreSection data={data} />
        <BusinessObjectiveSection data={data} />
        <TechnicalSubjectiveSection data={data} />
        <ResultSection data={data} />

        <footer className='mt-10 flex items-end justify-between border-t pt-6'>
          <div className='text-xs leading-6 text-muted-foreground'>
            交易大脑智能审核系统生成
            <br />
            报告编号：{data.projectInfo.reportNo}
          </div>
          <div className='text-center'>
            <div className='text-xs text-muted-foreground'>
              评标委员会（签章）
            </div>
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

function ResultSection({ data }: { data: TenderReviewMockData }) {
  const reasons = data.resultReasons ?? []
  const policyRefs = data.resultPolicyRefs ?? []
  const explanation =
    data.resultExplanation ||
    data.compareNotice?.explanation ||
    '评标结论生成后将在此展示。'
  const rejected = data.resultVerdict === 'rejected'

  return (
    <section className='mt-8'>
      <ReportTitle>综合得分与推荐结论</ReportTitle>
      <div className='mt-4 space-y-4'>
        <ScoreSummaryCard data={data} />
        <div className='rounded-lg border p-4'>
        <div className='flex flex-wrap items-center gap-2'>
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold ${
              rejected
                ? 'bg-red-100 text-red-700'
                : data.resultVerdict === 'manual_review'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-emerald-100 text-emerald-700'
            }`}
          >
            {getVerdictLabel(data.resultVerdict)}
          </span>
          {rejected ? (
            <span className='text-xs font-medium text-red-700'>
              整标废标，不进入有效投标评分排序
            </span>
          ) : null}
        </div>
        <p className='mt-3 text-sm leading-7 text-muted-foreground'>
          {explanation}
        </p>

        {reasons.length > 0 ? (
          <div className='mt-4'>
            <div className='text-sm font-semibold'>审核理由</div>
            <ul className='mt-2 space-y-1 text-sm leading-6 text-muted-foreground'>
              {reasons.map((reason, index) => (
                <li key={`${index}-${reason}`}>· {reason}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {policyRefs.length > 0 ? (
          <div className='mt-4'>
            <div className='text-sm font-semibold'>法定依据</div>
            <div className='mt-2 space-y-2'>
              {policyRefs.map((ref, index) => (
                <div
                  key={`${index}-${ref.id}`}
                  className='rounded-md bg-muted p-2'
                >
                  <div className='font-mono text-xs font-semibold text-foreground'>
                    {ref.id}
                    {ref.name ? ` · ${ref.name}` : ''}
                  </div>
                  {ref.sourceText ? (
                    <div className='mt-1 text-xs leading-5 text-muted-foreground'>
                      {ref.sourceText}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}
        <ComprehensiveOpinion data={data} />
        </div>
      </div>
    </section>
  )
}

function ScoreSummaryCard({ data }: { data: TenderReviewMockData }) {
  const summary = data.scoreSummary ?? emptyScoreSummary
  const deductedItems = [...summary.deductedItems, ...summary.rejectedItems]
  const hasScoring = (data.scoringItems?.length ?? 0) > 0

  return (
    <div className='w-full rounded-lg border bg-muted/30 p-4'>
      <div className='text-sm font-semibold'>评分汇总</div>
      <div className='mt-3 grid grid-cols-2 gap-3'>
        <ScoreMetric label='满分合计' value={formatScore(summary.maxTotal)} />
        <ScoreMetric
          label='实得合计'
          value={formatScore(summary.earnedTotal)}
        />
        <ScoreMetric
          label='扣分/未得分'
          value={`${formatScore(summary.deductedTotal)} 分 · ${deductedItems.length} 项`}
          items={deductedItems}
        />
        <ScoreMetric
          label='未计分项'
          value={`${formatScore(summary.pendingTotal)} 分 · ${summary.pendingItems.length} 项`}
          items={summary.pendingItems}
        />
      </div>
      {!hasScoring ? (
        <div className='mt-3 rounded-md border border-dashed p-2 text-xs text-muted-foreground'>
          暂无逐项评分数据。
        </div>
      ) : data.resultVerdict === 'rejected' ? (
        <div className='mt-3 rounded-md bg-red-50 p-2 text-xs leading-5 text-red-700'>
          综合意见按废标处理；下方评分明细仍完整展示，但不参与有效投标排序。
        </div>
      ) : null}
    </div>
  )
}

function ScoreMetric({
  label,
  value,
  items = [],
}: {
  label: string
  value: string
  items?: TenderScoreIssue[]
}) {
  return (
    <div className='min-w-0'>
      <div className='text-xs text-muted-foreground'>{label}</div>
      <div className='mt-1 text-lg font-semibold'>{value}</div>
      {items.length > 0 ? (
        <div className='mt-1 text-xs leading-5 text-muted-foreground'>
          {items.map((item) => item.item).join('、')}
        </div>
      ) : null}
    </div>
  )
}

function EligibilitySection({ data }: { data: TenderReviewMockData }) {
  const checks = data.resultEligibilityChecks ?? []

  return (
    <section className='mt-8'>
      <ReportTitle>资格性审查情况</ReportTitle>
      {checks.length > 0 ? (
        <div className='mt-4 overflow-hidden rounded-lg border'>
          <div className='grid grid-cols-[minmax(180px,1fr)_110px_minmax(220px,1.4fr)_160px] border-b bg-muted/40 px-3 py-2 text-xs font-semibold text-muted-foreground'>
            <div>审查项</div>
            <div className='text-center'>状态</div>
            <div>审查依据</div>
            <div>页码依据</div>
          </div>
          {checks.map((item, index) => (
            <div
              key={item.id}
              className={`grid grid-cols-[minmax(180px,1fr)_110px_minmax(220px,1.4fr)_160px] px-3 py-3 text-sm ${
                index % 2 ? 'bg-muted/20' : ''
              }`}
            >
              <div className='font-medium text-foreground'>{item.check}</div>
              <div className='text-center font-semibold'>
                {getEligibilityReportStatus(item.status)}
              </div>
              <div className='leading-6 text-muted-foreground'>
                {item.basis || '—'}
              </div>
              <div className='text-muted-foreground'>
                {getEvidenceSources(item.evidence)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptySectionText>暂无资格审查明细。</EmptySectionText>
      )}
    </section>
  )
}

function PriceScoreSection({ data }: { data: TenderReviewMockData }) {
  const items = getReportItems(data, 'price')
  const compare = data.comparePriceDetail

  return (
    <section className='mt-8'>
      <ReportTitle>价格分</ReportTitle>
      {compare ? (
        <div className='mt-4 space-y-4'>
          <div className='rounded-lg border bg-muted/30 p-4 text-sm leading-7 text-muted-foreground'>
            <div className='font-semibold text-foreground'>计算式</div>
            <div className='mt-1'>{compare.formula}</div>
            <EvidenceText evidence={compare.evidence} />
          </div>
          <div className='overflow-hidden rounded-lg border'>
            <div className='grid grid-cols-[minmax(180px,1fr)_150px_110px_120px] border-b bg-muted/40 px-3 py-2 text-xs font-semibold text-muted-foreground'>
              <div>投标人</div>
              <div>评标价/报价</div>
              <div className='text-center'>价格分</div>
              <div className='text-center'>状态</div>
            </div>
            {compare.cells.map((cell, index) => (
              <div
                key={cell.bidderId}
                className={`grid grid-cols-[minmax(180px,1fr)_150px_110px_120px] px-3 py-3 text-sm ${
                  index % 2 ? 'bg-muted/20' : ''
                }`}
              >
                <div className='font-medium text-foreground'>
                  {cell.bidderName}
                </div>
                <div className='text-muted-foreground'>{cell.bidPrice}</div>
                <div className='text-center font-semibold'>
                  {formatNullableScore(cell.score)}
                </div>
                <div className='text-center text-muted-foreground'>
                  {getScoringReportStatus(cell.status, cell.score)}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : items.length > 0 ? (
        <div className='mt-4 space-y-3'>
          {items.map((item) => (
            <div key={item.id} className='rounded-lg border p-4'>
              <div className='flex flex-wrap items-center justify-between gap-3'>
                <div>
                  <div className='font-semibold'>{item.item}</div>
                  <div className='mt-1 text-xs text-muted-foreground'>
                    满分 {formatScore(item.max)} 分
                  </div>
                </div>
                <div className='text-right'>
                  <div className='text-sm font-semibold'>
                    {item.score == null
                      ? '待全部投标报价一起计算'
                      : `${formatScore(item.score)} 分`}
                  </div>
                  <div className='mt-1 text-xs text-muted-foreground'>
                    {item.score == null ? '待补充' : getScoringReportStatus(item.status, item.score)}
                  </div>
                </div>
              </div>
              <div className='mt-3 text-sm leading-6 text-muted-foreground'>
                {item.basis || '需全部投标报价、评标基准价等横比输入后计算。'}
              </div>
              <EvidenceText evidence={item.evidence} />
            </div>
          ))}
        </div>
      ) : (
        <EmptySectionText>暂无价格分明细。</EmptySectionText>
      )}
    </section>
  )
}

function BusinessObjectiveSection({ data }: { data: TenderReviewMockData }) {
  const items = getReportItems(data, 'business_objective')
  const subtotal = getScoreSubtotal(items)

  return (
    <section className='mt-8'>
      <ReportTitle>商务客观分</ReportTitle>
      {items.length > 0 ? (
        <div className='mt-4 space-y-3'>
          <ScoreItemsTable items={items} />
          <div className='rounded-lg border bg-muted/30 p-3 text-sm font-semibold'>
            客观分小计：{formatScore(subtotal.score)} / {formatScore(subtotal.max)} 分
            {subtotal.pending > 0 ? (
              <span className='ml-2 font-normal text-muted-foreground'>
                {subtotal.pending} 项待补充，不按 0 分处理
              </span>
            ) : null}
          </div>
        </div>
      ) : (
        <EmptySectionText>暂无商务客观分明细。</EmptySectionText>
      )}
    </section>
  )
}

function TechnicalSubjectiveSection({ data }: { data: TenderReviewMockData }) {
  const items = getReportItems(data, 'technical_subjective')
  const rows = (data.compareScoreRows ?? []).filter(
    (row) => row.reviewDimension === 'technical_subjective'
  )

  return (
    <section className='mt-8'>
      <ReportTitle>技术主观分</ReportTitle>
      <div className='mt-2 text-xs font-medium text-amber-700'>
        初评建议，最终以评标委员会评分为准
      </div>
      {rows.length > 0 ? (
        <div className='mt-4 space-y-4'>
          {rows.map((row) => (
            <TechnicalCompareCard key={row.id} row={row} />
          ))}
        </div>
      ) : items.length > 0 ? (
        <div className='mt-4 space-y-3'>
          <ScoreItemsTable items={items} subjective />
          <div className='rounded-lg border border-dashed p-3 text-xs leading-5 text-muted-foreground'>
            横比数据不足，仅列示已有主观分与依据，不形成优劣判断。
          </div>
        </div>
      ) : (
        <EmptySectionText>暂无技术主观分明细。</EmptySectionText>
      )}
    </section>
  )
}

function getReportItems(
  data: TenderReviewMockData,
  dimension: TenderScoringItem['reviewDimension']
) {
  const items = data.scoringItems ?? []
  return items.filter((item) => item.reviewDimension === dimension)
}

function getScoreSubtotal(items: TenderScoringItem[]) {
  return {
    max: items.reduce((sum, item) => sum + item.max, 0),
    score: items.reduce((sum, item) => sum + (item.score ?? 0), 0),
    pending: items.filter((item) => item.score == null).length,
  }
}

function ScoreItemsTable({
  items,
  subjective = false,
}: {
  items: TenderScoringItem[]
  subjective?: boolean
}) {
  return (
    <div className='overflow-hidden rounded-lg border'>
      <div className='grid grid-cols-[minmax(180px,1fr)_80px_90px_minmax(220px,1.4fr)_150px] border-b bg-muted/40 px-3 py-2 text-xs font-semibold text-muted-foreground'>
        <div>评分项</div>
        <div className='text-center'>满分</div>
        <div className='text-center'>实得</div>
        <div>依据</div>
        <div>页码依据</div>
      </div>
      {items.map((item, index) => (
        <div
          key={item.id}
          className={`grid grid-cols-[minmax(180px,1fr)_80px_90px_minmax(220px,1.4fr)_150px] px-3 py-3 text-sm ${
            index % 2 ? 'bg-muted/20' : ''
          }`}
        >
          <div className='font-medium text-foreground'>
            {item.item}
            {subjective ? (
              <div className='mt-1 text-xs font-normal text-amber-700'>
                初评建议
              </div>
            ) : null}
          </div>
          <div className='text-center text-muted-foreground'>
            {formatScore(item.max)}
          </div>
          <div className='text-center font-semibold'>
            {formatNullableScore(item.score)}
          </div>
          <div className='leading-6 text-muted-foreground'>
            {item.basis || '—'}
          </div>
          <div className='text-muted-foreground'>
            {getEvidenceSources(item.evidence)}
          </div>
        </div>
      ))}
    </div>
  )
}

function TechnicalCompareCard({ row }: { row: TenderCompareScoreRow }) {
  const gridStyle = {
    gridTemplateColumns: `minmax(160px,1fr) repeat(${Math.max(
      row.cells.length,
      1
    )}, minmax(180px,1fr))`,
  }

  return (
    <div className='overflow-hidden rounded-lg border'>
      <div className='border-b bg-muted/40 px-4 py-3'>
        <div className='font-semibold'>{row.item}</div>
        <div className='mt-1 text-xs text-muted-foreground'>
          满分 {formatScore(row.max)} 分 · 初评建议，最终以评标委员会评分为准
        </div>
      </div>
      <div className='overflow-x-auto'>
        <div className='min-w-[680px]'>
          <div
            className='grid border-b px-4 py-2 text-xs font-semibold text-muted-foreground'
            style={gridStyle}
          >
            <div>对比项</div>
            {row.cells.map((cell) => (
              <div key={cell.bidderId}>{cell.bidderName}</div>
            ))}
          </div>
          <TechnicalCompareLine
            label='初评分'
            cells={row.cells.map((cell) => formatNullableScore(cell.score))}
            gridStyle={gridStyle}
          />
          <TechnicalCompareLine
            label='事实依据'
            cells={row.cells.map((cell) => cell.basis || '—')}
            gridStyle={gridStyle}
          />
          <TechnicalCompareLine
            label='页码依据'
            cells={row.cells.map((cell) => getEvidenceSources(cell.evidence))}
            gridStyle={gridStyle}
          />
        </div>
      </div>
      <div className='border-t px-4 py-3 text-sm leading-6 text-muted-foreground'>
        优劣差异：{buildSubjectiveDifference(row)}
      </div>
    </div>
  )
}

function TechnicalCompareLine({
  label,
  cells,
  gridStyle,
}: {
  label: string
  cells: string[]
  gridStyle: React.CSSProperties
}) {
  return (
    <div className='grid border-b px-4 py-3 text-sm last:border-b-0' style={gridStyle}>
      <div className='font-medium text-muted-foreground'>{label}</div>
      {cells.map((cell, index) => (
        <div key={`${label}-${index}`} className='leading-6 text-muted-foreground'>
          {cell}
        </div>
      ))}
    </div>
  )
}

function buildSubjectiveDifference(row: TenderCompareScoreRow) {
  const scored = row.cells.filter((cell) => cell.score != null)
  if (scored.length < 2) {
    return '分差暂无法计算，仅列示已返回的主观分与依据。'
  }
  const [left, right] = scored
  const diff = Math.abs((left.score ?? 0) - (right.score ?? 0))
  const scoreText =
    diff === 0
      ? `${left.bidderName}与${right.bidderName}分数相同`
      : `${left.bidderName}与${right.bidderName}分差 ${formatScore(diff)} 分`
  return `${scoreText}；依据对照：${left.bidderName}：${left.basis || '—'}；${right.bidderName}：${right.basis || '—'}。`
}

function EvidenceText({ evidence }: { evidence: TenderScoreEvidence[] }) {
  if (evidence.length === 0) return null
  return (
    <div className='mt-2 text-xs leading-5 text-muted-foreground'>
      {evidence.map((item, index) => (
        <div key={index}>
          {[item.source, item.finding, item.conclusion].filter(Boolean).join('：')}
        </div>
      ))}
    </div>
  )
}

function EmptySectionText({ children }: { children: React.ReactNode }) {
  return (
    <div className='mt-4 rounded-lg border border-dashed p-4 text-sm text-muted-foreground'>
      {children}
    </div>
  )
}

function getEvidenceSources(evidence: TenderScoreEvidence[]) {
  const sources = evidence.map((item) => item.source).filter(Boolean)
  return sources.length ? sources.join('、') : '—'
}

function getEligibilityReportStatus(status: TenderEligibilityCheck['status']) {
  if (status === 'pass' || status === 'passed') return '通过'
  if (status === 'fail' || status === 'failed' || status === 'rejected') {
    return '不通过'
  }
  return '待人工'
}

function getScoringReportStatus(status: string, score: number | null) {
  if (score == null || status === 'manual_review') return '待补充'
  if (status === 'rejected' || status === 'failed') return '未得分'
  if (status === 'scored') return '已评分'
  return status || '—'
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
          <div className='text-xs font-medium text-muted-foreground'>
            {label}
          </div>
          <div className='mt-1 text-sm font-semibold'>{value}</div>
        </div>
      ))}
    </section>
  )
}

function CompareNotice({ data }: { data: TenderReviewMockData }) {
  const notice = data.compareNotice
  if (
    !notice ||
    (!notice.stale && !notice.provisional && notice.warnings.length === 0)
  ) {
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
        {notice.stale ? (
          <div>投标人有变化，请重新横比后再展示推荐结论。</div>
        ) : null}
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

function ComprehensiveOpinion({ data }: { data: TenderReviewMockData }) {
  const winner = data.reviewBidders[0]
  const notice = data.compareNotice
  const second = data.reviewBidders[1]
  const third = data.reviewBidders[2]
  const failedEligibility = (data.resultEligibilityChecks ?? []).filter(
    (item) => item.status === 'fail' || item.status === 'failed'
  )
  if (data.resultVerdict === 'rejected') {
    return (
      <div className='mt-4 rounded-md bg-muted/40 p-4'>
        <div className='text-sm font-semibold'>评标委员会意见</div>
        <p className='mt-2 text-sm leading-8 text-muted-foreground'>
          经评审，
          {failedEligibility.length > 0 ? (
            <>
              本投标文件未通过资格审查（
              {failedEligibility.map((item) => item.check).join('、')}），
            </>
          ) : (
            <>本投标文件不满足本项目实质性响应要求，</>
          )}
          按废标处理。评分明细已继续逐项列示，仅作为过程记录，不参与有效投标排序。
          {data.resultExplanation ? (
            <>
              <br />
              <br />
              {data.resultExplanation}
            </>
          ) : null}
        </p>
      </div>
    )
  }

  return (
    <div className='mt-4 rounded-md bg-muted/40 p-4'>
      <div className='text-sm font-semibold'>评标委员会意见</div>
      <p className='mt-2 text-sm leading-8 text-muted-foreground'>
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
    </div>
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

const emptyScoreSummary = {
  maxTotal: 0,
  earnedTotal: 0,
  deductedTotal: 0,
  pendingTotal: 0,
  deductedItems: [],
  rejectedItems: [],
  pendingItems: [],
}

function getVerdictLabel(verdict: TenderReviewMockData['resultVerdict']) {
  if (verdict === 'approved') return '通过'
  if (verdict === 'rejected') return '废标'
  if (verdict === 'manual_review') return '需复核'
  return '未出结论'
}

function formatScore(score: number) {
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}

function formatNullableScore(score: number | null) {
  return score == null ? '待补充' : formatScore(score)
}
