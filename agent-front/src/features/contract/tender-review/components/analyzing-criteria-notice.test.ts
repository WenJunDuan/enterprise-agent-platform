/**
 * 分析中页对「收单等就绪」的交互兑现（2026-08-19 后端语义，commit b7f66cf）。
 *
 * 提交时 criteria 仍在解析不再 409：任务已受理，worker 在开跑判分前自己等就绪。用户点完
 * 「开始分析」落到本页，若这里只写「识别中」，他会以为自己点早了、要退回重传——等待感知
 * 必须写在状态区。反过来 criteria=failed 时任务会明确失败，页面不得再承诺"评标自行解析"。
 */
import { createElement } from 'react'
import { expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import type { TenderDocInfoResponse } from '../api'
import { AnalyzingView } from './analyzing-view'

function renderAnalyzing(
  criteriaStatus: TenderDocInfoResponse['criteria_status'],
  tenderOcrStatus: TenderDocInfoResponse['ocr_status'] = 'ready'
) {
  return renderToStaticMarkup(
    createElement(AnalyzingView, {
      progress: 30,
      docsStatus: {
        tender_doc: {
          ocr_status: tenderOcrStatus,
          criteria_status: criteriaStatus,
        },
        bids: [{ bid_id: 'bid-1', bidder_name: '甲公司', ocr_status: 'ready' }],
      },
      tenderDocInfo: {
        ocr_status: tenderOcrStatus,
        ocr_clarity: null,
        criteria_status: criteriaStatus,
        criteria: null,
        tender_info: null,
        tender_files: [],
      },
    })
  )
}

test('评分标准仍在解析时，分析中页要说明就绪后自动开始评分', () => {
  const markup = renderAnalyzing('running')

  expect(markup).toContain('自动开始评分')
  expect(markup).toContain('无需重新提交')
})

test('招标底稿还没识别完时同样给等待感知，而不是干等一句 OCR', () => {
  const markup = renderAnalyzing('pending', 'running')

  expect(markup).toContain('自动开始评分')
})

test('评分标准解析失败时，页面给重新上传动作，不再承诺评标自行解析', () => {
  const markup = renderAnalyzing('failed')

  expect(markup).toContain('重新上传招标文件')
  expect(markup).not.toContain('将以评标过程的解析结果为准')
})
