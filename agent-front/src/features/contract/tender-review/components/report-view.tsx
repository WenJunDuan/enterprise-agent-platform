import { ArrowLeft, Printer } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { getAdvisoryLabel } from '../model'
import type {
  IssueCategory,
  IssueItem,
  TenderCompareScoreRow,
  TenderEligibilityCheck,
  TenderReviewMockData,
  TenderScoreEvidence,
  TenderScoreIssue,
  TenderScoringItem,
  TenderScenario,
} from '../types'

type ReportViewProps = {
  data: TenderReviewMockData
  scenario?: TenderScenario
  onBack: () => void
  onConfirmDownloaded?: () => Promise<void> | void
}

export function ReportView({
  data,
  scenario = 'expert_assist',
  onBack,
  onConfirmDownloaded,
}: ReportViewProps) {
  const isSelfCheck = scenario === 'bidder_self_check'
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
          <Button
            type='button'
            size='sm'
            onClick={() => {
              if (isSelfCheck) void onConfirmDownloaded?.()
              else window.print()
            }}
          >
            <Printer className='size-4' />
            {isSelfCheck ? '下载并销毁' : '导出 PDF'}
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
        <ResultSection data={data} scenario={scenario} />

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

function ResultSection({
  data,
  scenario,
}: {
  data: TenderReviewMockData
  scenario: TenderScenario
}) {
  const policyRefs = data.resultPolicyRefs ?? []
  const issues = data.issueList ?? []
  const isSelfCheck = scenario === 'bidder_self_check'

  return (
    <section className='mt-8'>
      <ReportTitle>
        {isSelfCheck ? '自查风险、扣分点与修改建议' : '辅助评审与风险提示'}
      </ReportTitle>
      <div className='mt-4 space-y-4'>
        <ScoreSummaryCard data={data} />
        <IssueSummaryCard issues={issues} scenario={scenario} />
        <div className='rounded-lg border p-4'>
          {policyRefs.length > 0 ? (
            <div>
              <div className='text-sm font-semibold'>依据参考</div>
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
          ) : (
            <div className='text-sm text-muted-foreground'>
              暂无可展示的依据参考。
            </div>
          )}
          <ComprehensiveOpinion data={data} />
        </div>
      </div>
    </section>
  )
}

function IssueSummaryCard({
  issues,
  scenario,
}: {
  issues: IssueItem[]
  scenario: TenderScenario
}) {
  const isSelfCheck = scenario === 'bidder_self_check'
  const grouped = issueCategoryOrder
    .map((category) => ({
      category,
      label: issueCategoryLabels[category],
      items: issues.filter((issue) => issue.category === category),
    }))
    .filter((group) => group.items.length > 0)

  return (
    <div className='rounded-lg border bg-muted/30 p-4'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <div>
          <div className='text-sm font-semibold'>
            {isSelfCheck ? '自查问题与修改建议' : '问题清单摘要'}
          </div>
          <div className='mt-1 text-xs text-muted-foreground'>
            {getAdvisoryLabel(issues)}
          </div>
        </div>
        <div className='rounded-full bg-background px-3 py-1 text-xs font-semibold text-muted-foreground'>
          {issues.length} 项需关注
        </div>
      </div>
      {grouped.length > 0 ? (
        <div className='mt-4 space-y-4'>
          {grouped.map((group) => (
            <div key={group.category}>
              <div className='mb-2 text-xs font-semibold text-muted-foreground'>
                {group.label} · {group.items.length} 项
              </div>
              <div className='space-y-2'>
                {group.items.map((issue) => (
                  <div key={issue.id} className='rounded-md bg-background p-3 text-sm'>
                    <div className='font-semibold'>{issue.itemName}</div>
                    <div className='mt-1 leading-6 text-muted-foreground'>
                      {issue.basis}
                    </div>
                    {issue.quote ? (
                      <div className='mt-2 border-l-2 border-l-amber-300 pl-2 text-xs leading-5 text-muted-foreground italic'>
                        「{issue.quote}」
                      </div>
                    ) : null}
                    {issue.source ? (
                      <div className='mt-1 text-xs font-medium text-primary'>
                        {issue.source}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className='mt-3 rounded-md border border-dashed p-3 text-sm text-muted-foreground'>
          暂未发现明显问题；报告仅作为辅助评审材料。
        </div>
      )}
    </div>
  )
}

const issueCategoryOrder: IssueCategory[] = [
  'disqualification_risk',
  'eligibility_mismatch',
  'score_deduction',
  'formality_issue',
  'missing_material',
  'parameter_deviation',
  'pending_verification',
]

const issueCategoryLabels: Record<IssueCategory, string> = {
  disqualification_risk: '废标风险',
  eligibility_mismatch: '资格不符',
  score_deduction: '扣分点',
  formality_issue: '形式问题',
  missing_material: '材料缺失',
  parameter_deviation: '参数正负偏离',
  pending_verification: '待核验清单',
}

function ScoreSummaryCard({ data }: { data: TenderReviewMockData }) {
  const summary = data.scoreSummary ?? emptyScoreSummary
  const deductedItems = [...summary.deductedItems, ...summary.rejectedItems]
  const hasScoring = (data.scoringItems?.length ?? 0) > 0

  return (
    <div className='w-full rounded-lg border bg-muted/30 p-4'>
      <div className='text-sm font-semibold'>评审要素参考</div>
      <div className='mt-3 grid grid-cols-2 gap-3'>
        <ScoreMetric
          label='评审要素'
          value={`${data.scoringItems?.length ?? 0} 项`}
        />
        <ScoreMetric
          label='问题项'
          value={`${deductedItems.length} 项`}
          items={deductedItems}
        />
        <ScoreMetric
          label='待核验项'
          value={`${summary.pendingItems.length} 项`}
          items={summary.pendingItems}
        />
        <ScoreMetric
          label='展示口径'
          value='分值隐藏'
        />
      </div>
      {!hasScoring ? (
        <div className='mt-3 rounded-md border border-dashed p-2 text-xs text-muted-foreground'>
          暂无逐项评分数据。
        </div>
      ) : (
        <div className='mt-3 rounded-md bg-background p-2 text-xs leading-5 text-muted-foreground'>
          专家侧仅展示评审要素、问题项名和待核验项数；明确数值与排序不在本报告直显。
        </div>
      )}
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
            <div className='mt-1'>
              价格分由横比结果按招标文件价格公式统一计算；专家侧报告不直显分值。
            </div>
          </div>
          <div className='overflow-hidden rounded-lg border'>
            <div className='grid grid-cols-[minmax(180px,1fr)_150px_120px] border-b bg-muted/40 px-3 py-2 text-xs font-semibold text-muted-foreground'>
              <div>投标人</div>
              <div>评标价/报价</div>
              <div className='text-center'>状态</div>
            </div>
            {compare.cells.map((cell, index) => (
              <div
                key={cell.bidderId}
                className={`grid grid-cols-[minmax(180px,1fr)_150px_120px] px-3 py-3 text-sm ${
                  index % 2 ? 'bg-muted/20' : ''
                }`}
              >
                <div className='font-medium text-foreground'>
                  {cell.bidderName}
                </div>
                <div className='text-muted-foreground'>{cell.bidPrice}</div>
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
                      : '已完成内部计算'}
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
            商务客观评审要素：{items.length} 项
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
        <div className='text-center'>状态</div>
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
          <div className='text-center text-muted-foreground'>
            {getScoringReportStatus(item.status, item.score)}
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
        事实对照：仅列各投标人依据与出处，不形成分值判断。
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
  if (status === 'rejected' || status === 'failed') return '存在问题'
  if (status === 'scored') return '已评分'
  return status || '—'
}

function ReportMeta({ data }: { data: TenderReviewMockData }) {
  const meta = [
    ['项目名称', data.projectInfo.name],
    ['招标编号', data.projectInfo.code],
    ['评标办法', data.projectInfo.method],
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
            ? '横比结果待定'
            : '横比告警'}
      </AlertTitle>
      <AlertDescription className='mt-2 space-y-1'>
        {notice.stale ? (
          <div>投标人有变化，请重新横比后再展示横比结果。</div>
        ) : null}
        {notice.provisional ? (
          <div>横比结果仍需复核，定标由招标人依法确定。</div>
        ) : null}
        {notice.warnings.map((warning) => (
          <div key={warning}>{warning}</div>
        ))}
      </AlertDescription>
    </Alert>
  )
}

function ComprehensiveOpinion({ data }: { data: TenderReviewMockData }) {
  const notice = data.compareNotice
  const issues = data.issueList ?? []
  const pendingCount = issues.filter((issue) => issue.status === 'pending').length

  return (
    <div className='mt-4 rounded-md bg-muted/40 p-4'>
      <div className='text-sm font-semibold'>辅助评审意见</div>
      <p className='mt-2 text-sm leading-8 text-muted-foreground'>
        本报告面向专家辅助评审，仅列示从投标文件与招标文件派生的问题线索。
        {issues.length > 0 ? (
          <>
            当前共形成 <b className='text-foreground'>{issues.length}</b>{' '}
            项需关注内容，其中 <b className='text-foreground'>{pendingCount}</b>{' '}
            项待核验；请结合问题清单、命中原文与出处页复核。
          </>
        ) : (
          <>暂未发现明显问题，仍建议按评审程序抽查关键原文。</>
        )}
        {notice?.warnings.length ? (
          <>
            <br />
            <br />
            需提请注意：{notice.warnings.join('；')}
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
  deductedItems: [],
  rejectedItems: [],
  pendingItems: [],
}

function formatScore(score: number) {
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}
