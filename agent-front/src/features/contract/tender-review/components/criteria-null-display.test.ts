import { createElement } from 'react'
import { expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import type {
  TenderReviewMockData,
  TenderScoreSummary,
  TenderScoringItem,
} from '../types'
import { AnalyzingView } from './analyzing-view'
import { BidderCompareCards } from './bidder-compare-cards'
import { ReportView } from './report-view'
import { ScoringDetailTable } from './scoring-detail-table'
import { ScoringOverviewPanel } from './scoring-overview-panel'

const manualItem: TenderScoringItem = {
  id: 'manual-1',
  item: '现场答辩',
  max: null,
  score: null,
  status: 'manual_review',
  basis: '待现场确认。',
  category: '技术标',
  scoreCategory: 'technical',
  reviewDimension: 'technical_subjective',
  scoreMode: 'manual',
  evidence: [],
}

const summary: TenderScoreSummary = {
  knownMaxTotal: 70,
  unknownMaxCount: 2,
  maxTotal: null,
  earnedTotal: 56,
  deductedTotal: 14,
  pendingTotal: 0,
  deductedItems: [],
  rejectedItems: [],
  pendingItems: [
    {
      item: manualItem.item,
      max: null,
      score: null,
      status: manualItem.status,
      deduction: null,
      basis: manualItem.basis,
      scoreCategory: manualItem.scoreCategory,
      reviewDimension: manualItem.reviewDimension,
    },
  ],
  categorySummaries: [
    {
      category: 'business',
      knownMaxTotal: 70,
      unknownMaxCount: 0,
      maxTotal: 70,
      score: 56,
    },
    {
      category: 'technical',
      knownMaxTotal: 0,
      unknownMaxCount: 2,
      maxTotal: null,
      score: 0,
    },
  ],
}

test('criteria and scoring components render unknown max as 未设分值 and total as 待确认', () => {
  const analyzing = renderToStaticMarkup(
    createElement(AnalyzingView, {
      progress: 50,
      tenderDocInfo: {
        ocr_status: 'ready',
        ocr_clarity: 'high',
        criteria_status: 'ready',
        criteria: {
          total_max: 100,
          items: [
            { item: '技术', max: 70 },
            {
              item: '现场答辩',
              max: null,
              tag: 'requires_live_event',
              score_mode: 'manual',
            },
          ],
        },
        tender_info: null,
        tender_files: [],
      },
    })
  )
  const detail = renderToStaticMarkup(
    createElement(ScoringDetailTable, { items: [manualItem] })
  )
  const overview = renderToStaticMarkup(
    createElement(ScoringOverviewPanel, {
      projectInfo: {
        name: '测试项目',
        code: 'T-1',
        method: '综合评估法',
        controlPrice: '-',
        reviewDate: '',
        reportNo: '',
      },
      bidderName: '投标人甲',
      scoreSummary: summary,
      scoringItems: [manualItem],
    })
  )

  expect(analyzing).toContain('未设分值')
  expect(analyzing).toContain('待确认')
  expect(detail).toContain('未设分值')
  expect(overview).toContain('待确认')
  expect(overview).toContain('未设分值')
  expect(overview.replaceAll('<!-- -->', '')).toContain('56 / 70')
})

test('report does not present a null max as zero', () => {
  const data = {
    projectInfo: {
      name: '测试项目',
      code: 'T-1',
      method: '综合评估法',
      controlPrice: '-',
      reviewDate: '',
      reportNo: '',
    },
    tenderFiles: [],
    uploadBidders: [],
    reviewBidders: [],
    projects: [],
    categories: [],
    paragraphs: [],
    compareGroups: [],
    scoringItems: [manualItem],
    scoreSummary: summary,
  } as TenderReviewMockData

  const markup = renderToStaticMarkup(
    createElement(ReportView, { data, onBack: () => {} })
  )

  expect(markup).toContain('未设分值')
  expect(markup).not.toContain('满分 0 分')
})

test('blocked bidder card shows pending total without inventing a rank', () => {
  const markup = renderToStaticMarkup(
    createElement(BidderCompareCards, {
      cards: [
        {
          id: 'CLAIM-BLOCKED',
          tag: '甲',
          name: '待复核投标人',
          short: '待复核',
          total: null,
          rank: null,
          score: summary,
          checklist: [],
          topIssues: [],
        },
      ],
    })
  )

  expect(markup).toContain('>待确认<')
  expect(markup).not.toContain('>56<')
  expect(markup).not.toContain('第 1 名')
})
