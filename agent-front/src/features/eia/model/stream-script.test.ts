import { describe, expect, test } from 'bun:test'
import {
  buildStreamScript,
  buildTrackRows,
  computeProgressPercent,
  isStreamDone,
  visibleLines,
  type StreamScriptLine,
} from './stream-script'

// 流式脚本引擎：静态稿 buildScript() + renderVals() 里字符偏移推进逻辑的无副作用重写
// (design.md A3「流式引擎纯函数化」)。输入 chars 计数 → 输出可见行 / 分轨状态 / 进度，
// setInterval 只留在组件层，这里可脱离 DOM 直接单测（与 job-model.ts 同一纪律）。

const WATER_LINES: StreamScriptLine[] = [
  { text: '解析水质监测数据', tone: 'cat' },
  { text: 'pH 7.2 达标', tone: 'data' },
]
const AIR_LINES: StreamScriptLine[] = [
  { text: '解析废气监测数据', tone: 'cat' },
  { text: '非甲烷总烃关注', tone: 'warn' },
]
const CATEGORY_LINES = { water: WATER_LINES, air: AIR_LINES }

describe('buildStreamScript', () => {
  test('assembles header + per-category chunks + tail in category order, ignoring inactive categories', () => {
    const script = buildStreamScript(['air', 'water'], CATEGORY_LINES, 3)

    // water 排在 air 前（固定类别顺序），soil/noise 未激活不出现在脚本里。
    expect(script.activeCategories).toEqual(['water', 'air'])
    expect(script.lines.map((line) => line.text)).toEqual([
      expect.stringContaining('3'),
      expect.stringContaining('校验'),
      '解析水质监测数据',
      'pH 7.2 达标',
      '解析废气监测数据',
      '非甲烷总烃关注',
      expect.stringContaining('汇总'),
      expect.stringContaining('✓'),
    ])
  })

  test('computes monotonically increasing offsets that sum to totalChars', () => {
    const script = buildStreamScript(['water'], CATEGORY_LINES, 2)

    expect(script.offsets).toHaveLength(script.lines.length)
    for (let i = 1; i < script.offsets.length; i++) {
      expect(script.offsets[i]).toBeGreaterThan(script.offsets[i - 1])
    }
    const lastLine = script.lines[script.lines.length - 1]
    const lastOffset = script.offsets[script.offsets.length - 1]
    expect(lastOffset + lastLine.text.length + 1).toBe(script.totalChars)
  })

  test('records catStart/tailStart line indices for track-row lookups', () => {
    const script = buildStreamScript(['water', 'air'], CATEGORY_LINES, 4)

    expect(script.lines[script.catStart.water ?? -1]?.text).toBe(
      '解析水质监测数据'
    )
    expect(script.lines[script.catStart.air ?? -1]?.text).toBe(
      '解析废气监测数据'
    )
    expect(script.lines[script.tailStart].text).toContain('汇总')
  })

  test('empty active categories still produces a valid (header + tail only) script', () => {
    const script = buildStreamScript([], CATEGORY_LINES, 0)
    expect(script.activeCategories).toEqual([])
    expect(script.lines.length).toBeGreaterThan(0)
    expect(script.totalChars).toBeGreaterThan(0)
  })
})

describe('visibleLines', () => {
  test('reveals nothing before the first line starts', () => {
    const script = buildStreamScript(['water'], CATEGORY_LINES, 1)
    expect(visibleLines(script, 0)).toEqual([])
  })

  test('reveals a line partially with a trailing cursor while mid-line', () => {
    const script = buildStreamScript(['water'], CATEGORY_LINES, 1)
    const firstLineLength = script.lines[0].text.length
    const partialChars = script.offsets[0] + Math.floor(firstLineLength / 2)

    const lines = visibleLines(script, partialChars)
    const lastVisible = lines[lines.length - 1]

    expect(lastVisible.text.length).toBeLessThan(firstLineLength)
    expect(lastVisible.text.length).toBeGreaterThan(0)
    expect(lastVisible.cursor).toBe(true)
  })

  test('reveals every line in full once chars reaches totalChars, no cursor left', () => {
    const script = buildStreamScript(['water'], CATEGORY_LINES, 1)
    const lines = visibleLines(script, script.totalChars)

    expect(lines.map((line) => line.text)).toEqual(
      script.lines.map((line) => line.text)
    )
    expect(lines[lines.length - 1].cursor).toBe(false)
  })
})

describe('computeProgressPercent', () => {
  test('clamps to 0-100 and rounds to whole percent', () => {
    const script = buildStreamScript(['water'], CATEGORY_LINES, 1)

    expect(computeProgressPercent(script, 0)).toBe(0)
    expect(computeProgressPercent(script, script.totalChars)).toBe(100)
    expect(computeProgressPercent(script, script.totalChars * 2)).toBe(100)
  })
})

describe('isStreamDone', () => {
  test('is false until chars reaches totalChars, true at and beyond', () => {
    const script = buildStreamScript(['water'], CATEGORY_LINES, 1)

    expect(isStreamDone(script, script.totalChars - 1)).toBe(false)
    expect(isStreamDone(script, script.totalChars)).toBe(true)
  })
})

describe('buildTrackRows', () => {
  test('progresses header -> category -> tail from 等待 to 进行中 to 完成', () => {
    const script = buildStreamScript(['water'], CATEGORY_LINES, 1)

    const beforeStart = buildTrackRows(script, 0)
    expect(beforeStart.map((row) => row.status)).toEqual([
      '等待',
      '等待',
      '等待',
    ])

    const midCategory = buildTrackRows(
      script,
      script.offsets[script.catStart.water ?? 0] + 1
    )
    expect(midCategory[0].status).toBe('完成')
    expect(midCategory[1].status).toBe('进行中')
    expect(midCategory[2].status).toBe('等待')

    const done = buildTrackRows(script, script.totalChars)
    expect(done.every((row) => row.status === '完成')).toBe(true)
  })
})
