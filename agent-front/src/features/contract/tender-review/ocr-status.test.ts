import { expect, test } from 'bun:test'
import {
  criteriaWaitingHint,
  isOcrImpaired,
  isOcrTerminal,
  isOcrUsable,
  ocrDotClass,
  ocrImpairedNotice,
  ocrStatusLabel,
} from './ocr-status'

// H3 KD2 前端硬门：doc 层新增 degraded/partial 两档。这些谓词是终态集/canStart/状态点/文案的
// 唯一判据源——漏接一档的后果是"轮询永不终止 + 开始分析永久禁用"（用户被锁死）。

test('degraded 与 partial 是终态，轮询必须停', () => {
  expect(isOcrTerminal('ready')).toBe(true)
  expect(isOcrTerminal('failed')).toBe(true)
  expect(isOcrTerminal('degraded')).toBe(true)
  expect(isOcrTerminal('partial')).toBe(true)
  expect(isOcrTerminal('running')).toBe(false)
  expect(isOcrTerminal('pending')).toBe(false)
})

test('degraded 与 partial 底稿可用，可以开始分析', () => {
  expect(isOcrUsable('ready')).toBe(true)
  expect(isOcrUsable('degraded')).toBe(true)
  expect(isOcrUsable('partial')).toBe(true)
  expect(isOcrUsable('failed')).toBe(false)
  expect(isOcrUsable('running')).toBe(false)
})

test('只有降级/部分缺失才算受损（ready 与 failed 都不是）', () => {
  expect(isOcrImpaired('degraded')).toBe(true)
  expect(isOcrImpaired('partial')).toBe(true)
  expect(isOcrImpaired('ready')).toBe(false)
  expect(isOcrImpaired('failed')).toBe(false)
})

test('每个状态都有中文 label，未知值原样回显而不是空白', () => {
  expect(ocrStatusLabel('ready')).toBe('已就绪')
  expect(ocrStatusLabel('degraded')).toBe('已就绪（降级识别）')
  expect(ocrStatusLabel('partial')).toBe('部分完成')
  expect(ocrStatusLabel('failed')).toBe('识别失败')
  expect(ocrStatusLabel('running')).toBe('识别中')
  expect(ocrStatusLabel('pending')).toBe('等待中')
  expect(ocrStatusLabel('surprise')).toBe('surprise')
})

test('degraded 状态点不得显示"进行中"的蓝色脉冲', () => {
  expect(ocrDotClass('running')).toContain('animate-pulse')
  expect(ocrDotClass('degraded')).not.toContain('animate-pulse')
  expect(ocrDotClass('partial')).not.toContain('animate-pulse')
  expect(ocrDotClass('degraded')).toContain('amber')
  expect(ocrDotClass('partial')).toContain('amber')
  expect(ocrDotClass('ready')).toContain('emerald')
  expect(ocrDotClass('failed')).toContain('red')
})

// 2026-08-19 收单等就绪：提交时 criteria 仍在解析不再 409，任务自己等就绪再判分。
// 分析中页必须把这件事说出来，否则用户看到「识别中」会以为自己点早了、要重来。
test('评分标准仍在解析时，提示必须说清就绪后自动开始评分', () => {
  expect(criteriaWaitingHint('ready')).toContain('自动开始评分')
  expect(criteriaWaitingHint('pending')).toContain('自动开始评分')
})

test('招标底稿尚不可用与已可用给不同的进度说明', () => {
  expect(criteriaWaitingHint('ready')).toContain('抽取')
  expect(criteriaWaitingHint('running')).toContain('OCR')
  expect(criteriaWaitingHint('degraded')).toContain('抽取')
})

test('底稿受损时给出告警文案，全 ready 时不给', () => {
  const docs = {
    tender_doc: { ocr_status: 'ready' as const, criteria_status: 'ready' as const },
    bids: [
      { bid_id: 'b1', bidder_name: '甲', ocr_status: 'partial' as const },
      { bid_id: 'b2', bidder_name: null, ocr_status: 'ready' as const },
    ],
  }
  const notice = ocrImpairedNotice(docs)
  expect(notice).not.toBeNull()
  expect(notice).toContain('甲')

  expect(
    ocrImpairedNotice({
      tender_doc: { ocr_status: 'ready', criteria_status: 'ready' },
      bids: [{ bid_id: 'b1', bidder_name: '甲', ocr_status: 'ready' }],
    })
  ).toBeNull()
  expect(ocrImpairedNotice(null)).toBeNull()
})
