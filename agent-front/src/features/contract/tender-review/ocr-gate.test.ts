import { createElement } from 'react'
import { expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import type { DocsStatusResponse } from './api'
import { AnalyzingView } from './components/analyzing-view'
import { isOcrTerminal, isOcrUsable } from './ocr-status'

// H3 AC6b：doc 状态 degraded/partial 必须在前端全链路可见且不锁死用户。

function docs(bidStatus: DocsStatusResponse['bids'][number]['ocr_status']): DocsStatusResponse {
  return {
    tender_doc: { ocr_status: 'ready', criteria_status: 'ready' },
    bids: [{ bid_id: 'b1', bidder_name: '投标人甲', ocr_status: bidStatus }],
  }
}

/** 复刻 use-tender-review-page 的轮询终止判据（同一组谓词，防两处漂移）。 */
function pollingStops(status: DocsStatusResponse): boolean {
  return (
    status.bids.length > 0 &&
    isOcrTerminal(status.tender_doc?.ocr_status ?? 'pending') &&
    status.bids.every((bid) => isOcrTerminal(bid.ocr_status))
  )
}

/** 复刻 isOcrReady 判据。 */
function canStart(status: DocsStatusResponse): boolean {
  return (
    isOcrUsable(status.tender_doc?.ocr_status ?? 'pending') &&
    status.bids.length > 0 &&
    status.bids.every((bid) => isOcrUsable(bid.ocr_status))
  )
}

test('degraded/partial 底稿让轮询正常终止', () => {
  expect(pollingStops(docs('degraded'))).toBe(true)
  expect(pollingStops(docs('partial'))).toBe(true)
  expect(pollingStops(docs('running'))).toBe(false)
})

test('degraded/partial 底稿不禁用「开始分析」', () => {
  expect(canStart(docs('degraded'))).toBe(true)
  expect(canStart(docs('partial'))).toBe(true)
  expect(canStart(docs('failed'))).toBe(false)
})

test('区2 状态行显示降级 label 与非蓝色状态点', () => {
  const markup = renderToStaticMarkup(
    createElement(AnalyzingView, {
      progress: 40,
      progressByRid: {},
      activeEval: null,
      docsStatus: {
        tender_doc: { ocr_status: 'degraded', criteria_status: 'ready' },
        bids: [{ bid_id: 'b1', bidder_name: '投标人甲', ocr_status: 'partial' }],
      },
      tenderDocInfo: null,
    })
  )

  expect(markup).toContain('已就绪（降级识别）')
  expect(markup).toContain('amber')
  expect(markup).not.toContain('bg-blue-400 animate-pulse')
})

test('招标底稿 degraded 时不再显示"等待招标文件 OCR 完成"', () => {
  const markup = renderToStaticMarkup(
    createElement(AnalyzingView, {
      progress: 40,
      progressByRid: {},
      activeEval: null,
      docsStatus: {
        tender_doc: { ocr_status: 'degraded', criteria_status: 'running' },
        bids: [{ bid_id: 'b1', bidder_name: '投标人甲', ocr_status: 'ready' }],
      },
      tenderDocInfo: { criteria_status: 'running', criteria: null, tender_info: null },
    })
  )

  expect(markup).not.toContain('等待招标文件 OCR 完成')
})
