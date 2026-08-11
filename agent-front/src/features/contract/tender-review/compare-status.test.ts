/**
 * KD2 前端消费横比生命周期 + KD5 pending_reason 文案映射。
 *
 * 锁定：
 * - `TenderCompareResponse` 带 status/error_detail、result 可为 null（GET 恒 200，不再有 404 分支）；
 * - compareNotice 透出 status + errorDetail，失败态可解释；
 * - 评分项 pending_reason 映射为中文文案，存量无该字段的结果按 tag/status 兜底不回归。
 */
import { describe, expect, test } from 'bun:test'
import {
  PENDING_REASON_LABELS,
  buildTenderReviewData,
  describeCompareTriggerError,
  resolvePendingReasonLabel,
} from './model'
import type { TenderCompareResponse, TenderProjectDetailResponse } from './api'
import type { AuditResult } from '@/features/audit/types'

const PROJECT: TenderProjectDetailResponse = {
  project_id: 'tp-1',
  scenario: 'tender',
  tender_no: 'R-001',
  title: '某系统采购',
  tenderee: '某单位',
  method: '综合评估法',
  control_price: null,
  funding_type: 'state_funded',
  status: 'review',
  created_at: '2026-08-11T00:00:00+00:00',
  updated_at: '2026-08-11T00:00:00+00:00',
  bidder_count: 2,
  bids: [],
}

function compareResponse(
  overrides: Partial<TenderCompareResponse>
): TenderCompareResponse {
  return {
    project_id: 'tp-1',
    status: 'ready',
    error_detail: null,
    result: null,
    stale: false,
    ...overrides,
  }
}

describe('compare 生命周期', () => {
  test('failed 状态透出脱敏原因，可解释', () => {
    const data = buildTenderReviewData({
      project: PROJECT,
      compare: compareResponse({
        status: 'failed',
        error_detail: '横比调用超时',
      }),
    })
    expect(data.compareNotice?.status).toBe('failed')
    expect(data.compareNotice?.errorDetail).toBe('横比调用超时')
  })

  test('running 状态不当成失败，也不谎报已就绪', () => {
    const data = buildTenderReviewData({
      project: PROJECT,
      compare: compareResponse({ status: 'running' }),
    })
    expect(data.compareNotice?.status).toBe('running')
    expect(data.compareNotice?.errorDetail).toBeUndefined()
  })

  test('result 为 null 时不崩、不伪造推荐', () => {
    const data = buildTenderReviewData({
      project: PROJECT,
      compare: compareResponse({ status: 'none' }),
    })
    expect(data.compareNotice?.recommended).toBeNull()
    expect(data.compareGroups).toEqual([])
  })
})

describe('pending_reason 文案', () => {
  const result = (scoring: Record<string, unknown>[]): AuditResult =>
    ({
      claim_id: 'B1',
      verdict: 'manual_review',
      explanation: '价格项待横比。',
      reasons: [],
      policy_refs: [],
      risk_score: 10,
      evidence_chain: [],
      reviewed_by: 'tender-evaluator',
      timestamp: '2026-08-11T00:00:00+00:00',
      extracted_data: { scoring },
    }) as unknown as AuditResult

  test('六个枚举都有中文文案', () => {
    expect(Object.keys(PENDING_REASON_LABELS).sort()).toEqual([
      'cross_bid',
      'evidence_unresolved',
      'external_data',
      'live_event',
      'manual_mode',
      'non_responsive',
    ])
  })

  test('评分项带 pending_reason → 映射到对应文案', () => {
    const data = buildTenderReviewData({
      project: PROJECT,
      selectedResult: result([
        {
          item: '价格分',
          max: 40,
          score: null,
          status: 'manual_review',
          pending_reason: 'cross_bid',
        },
      ]),
    })
    const item = data.scoringItems?.[0]
    expect(item?.pendingReason).toBe('cross_bid')
    expect(resolvePendingReasonLabel(item)).toBe(
      PENDING_REASON_LABELS.cross_bid
    )
  })

  test('存量结果无 pending_reason → 仍显示待核验，不回归', () => {
    const data = buildTenderReviewData({
      project: PROJECT,
      selectedResult: result([
        { item: '答辩', max: 10, score: null, status: 'manual_review' },
      ]),
    })
    const item = data.scoringItems?.[0]
    expect(item?.pendingReason).toBeUndefined()
    expect(resolvePendingReasonLabel(item)).toBe('待核验')
  })

  test('未知枚举值不透传（防脏数据直接上屏）', () => {
    const data = buildTenderReviewData({
      project: PROJECT,
      selectedResult: result([
        {
          item: '答辩',
          max: 10,
          score: null,
          status: 'manual_review',
          pending_reason: 'whatever',
        },
      ]),
    })
    expect(data.scoringItems?.[0]?.pendingReason).toBeUndefined()
  })

  test('已评分项不显示待核验文案', () => {
    const data = buildTenderReviewData({
      project: PROJECT,
      selectedResult: result([
        { item: '技术', max: 60, score: 50, status: 'scored' },
      ]),
    })
    expect(resolvePendingReasonLabel(data.scoringItems?.[0])).toBe('已记录')
  })
})

describe('重新横比触发（M1）', () => {
  test('409「正在进行中」视作已触发 → 静默，不打扰用户', () => {
    expect(
      describeCompareTriggerError(
        new Error('该招标项目横比正在进行中，请稍后查看结果')
      )
    ).toBeNull()
  })

  test('其余失败给可读原因（错误可解释）', () => {
    expect(describeCompareTriggerError(new Error('参与横比的已完成投标人不足 2 家'))).toBe(
      '参与横比的已完成投标人不足 2 家'
    )
    expect(describeCompareTriggerError('boom')).toBe('请稍后重试')
  })
})
