/**
 * S1 · 降级可见（sprint 2026-08-15-tender-context-pipeline，AC2/AC3 前端侧）。
 *
 * 三次事故的共同放大器是静默：底稿链路掉回 inline OCR、criteria 抽取失败，用户在界面上
 * 要么什么都看不到，要么只看到一句"识别失败"。这里的断言保证两类降级都上界面。
 */
import { expect, test } from 'bun:test'

import { buildIssueList } from './model'
import { criteriaProblemNotice } from './ocr-status'

test('底稿链路掉落 inline 时，结论页必须出现可见告警条目', () => {
  const issues = buildIssueList({
    extracted_data: {
      ocr_warnings: [
        {
          scope: '评标底稿链路',
          status: 'doc_layer_fallback',
          reason: 'missing_bid_id',
          files: [],
          message: '未复用预热底稿（提交时未能定位本次投标的预热记录；原因码 missing_bid_id），已改用即时 OCR 重新识别本案目录；证据出处与页锚可能与预热底稿不一致，耗时也显著更长。',
        },
      ],
    },
  })

  const degraded = issues.filter((item) => item.category === 'pipeline_degraded')
  expect(degraded.length).toBe(1)
  expect(degraded[0].status).toBe('warning')
  expect(degraded[0].basis).toContain('missing_bid_id')
  expect(degraded[0].itemName).toBe('评标底稿链路')
})

test('底稿部分缺失的既有 warning 同样上界面（不只掉落一种）', () => {
  const issues = buildIssueList({
    extracted_data: {
      ocr_warnings: [
        {
          scope: '投标文件',
          status: 'partial',
          files: ['技术标.pdf'],
          message: '投标文件底稿部分文件识别失败或缺页：技术标.pdf；依赖这些材料的评分项证据可能不完整。',
        },
      ],
    },
  })

  expect(issues.filter((item) => item.category === 'pipeline_degraded').length).toBe(1)
})

test('无降级时不得凭空造告警（否则告警会被无视）', () => {
  expect(
    buildIssueList({ extracted_data: { ocr_warnings: [] } }).filter(
      (item) => item.category === 'pipeline_degraded'
    ).length
  ).toBe(0)
  expect(
    buildIssueList({ extracted_data: {} }).filter(
      (item) => item.category === 'pipeline_degraded'
    ).length
  ).toBe(0)
})

test('criteria 抽取失败时，提示要说清缺什么而不是只说"识别失败"', () => {
  const notice = criteriaProblemNotice({
    tender_doc: {
      ocr_status: 'ready',
      criteria_status: 'failed',
      criteria_error: '评分标准的 items 评分项为空（items_empty）',
    },
    bids: [],
  })
  expect(notice).toContain('items_empty')
  expect(notice).toContain('评分项为空')
})

// 2026-08-19 收单等就绪：criteria=failed 在提交口仍是 409 硬拒（criteria_gate.
// criteria_submission_block）。旧文案「分析仍可开始，评标会自行解析招标文件」已与后端相反，
// 照它做只会撞一次 409。
test('criteria 解析失败的提示必须给出重新上传动作，不得再说分析仍可开始', () => {
  const notice = criteriaProblemNotice({
    tender_doc: { ocr_status: 'ready', criteria_status: 'failed' },
    bids: [],
  })

  expect(notice).toContain('重新上传招标文件')
  expect(notice).not.toContain('分析仍可开始')
})

test('criteria 失败但后端没给原因时仍要提示，不能静默', () => {
  const notice = criteriaProblemNotice({
    tender_doc: { ocr_status: 'ready', criteria_status: 'failed' },
    bids: [],
  })
  expect(notice).not.toBeNull()
})

test('criteria 正常时无提示', () => {
  expect(
    criteriaProblemNotice({
      tender_doc: { ocr_status: 'ready', criteria_status: 'ready' },
      bids: [],
    })
  ).toBeNull()
  expect(criteriaProblemNotice(null)).toBeNull()
})
