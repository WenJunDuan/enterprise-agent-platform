import { EIA_CATEGORY_ORDER, type EiaCategory } from '../types'

// 流式脚本引擎：静态稿 buildScript()/renderVals() 里的字符偏移推进逻辑抽成的无副作用纯函数
// (design.md A3「流式引擎纯函数化」)。setInterval 只留在组件层(useEffect cleanup 归口)，
// 这里只吃 chars 计数、吐可见行/进度/分轨状态，可脱离 DOM 直接单测，与 job-model.ts 同一纪律。

export type StreamTone = 'head' | 'cat' | 'data' | 'ok' | 'warn'

export interface StreamScriptLine {
  text: string
  tone: StreamTone
}

export interface CompiledStreamScript {
  lines: StreamScriptLine[]
  offsets: number[]
  totalChars: number
  catStart: Partial<Record<EiaCategory, number>>
  tailStart: number
  activeCategories: EiaCategory[]
}

/**
 * 按 water/soil/air/noise 固定顺序拼装：载入校验(头) + 每个已激活类别的分析台词
 * (categoryLines 供数，来自 mock-data.ts 的演示内容) + 汇总编制(尾)。
 *
 * @param activeCategories - 本次已上传材料的类别(顺序不敏感，内部按固定类别顺序重排)。
 * @param categoryLines - 每个类别的分析台词行；未提供的类别按空数组处理。
 * @param totalFiles - 材料总数，写进头部台词展示。
 */
export function buildStreamScript(
  activeCategories: EiaCategory[],
  categoryLines: Partial<Record<EiaCategory, StreamScriptLine[]>>,
  totalFiles: number
): CompiledStreamScript {
  const orderedActive = EIA_CATEGORY_ORDER.filter((category) =>
    activeCategories.includes(category)
  )

  const lines: StreamScriptLine[] = [
    {
      text: `受理编号 · 载入材料 ${totalFiles} 份,识别类别 ${orderedActive.length} 项`,
      tone: 'head',
    },
    { text: '校验文件格式、签章与完整性 …… 通过', tone: 'head' },
  ]

  const catStart: Partial<Record<EiaCategory, number>> = {}
  for (const category of orderedActive) {
    catStart[category] = lines.length
    lines.push(...(categoryLines[category] ?? []))
  }

  const tailStart = lines.length
  lines.push({ text: '汇总各类结论,编制分类分析报告 ……', tone: 'head' })
  lines.push({
    text: `✓ 分析完成 · 共出具 ${orderedActive.length} 份分类报告,已同步受理工作台`,
    tone: 'ok',
  })

  let acc = 0
  const offsets = lines.map((line) => {
    const start = acc
    acc += line.text.length + 1
    return start
  })

  return {
    lines,
    offsets,
    totalChars: acc,
    catStart,
    tailStart,
    activeCategories: orderedActive,
  }
}

export interface VisibleStreamLine {
  text: string
  tone: StreamTone
  cursor: boolean
}

/** 给定当前已「流出」的字符数，逐行裁出可见文本；命中未写完的一行即停止(尾随光标)。 */
export function visibleLines(
  script: CompiledStreamScript,
  chars: number
): VisibleStreamLine[] {
  const result: VisibleStreamLine[] = []

  for (let i = 0; i < script.lines.length; i++) {
    const start = script.offsets[i]
    if (chars <= start) break

    const { text, tone } = script.lines[i]
    const shown = Math.min(text.length, chars - start)
    const partial = shown < text.length
    const isLast = i === script.lines.length - 1
    const nextStart = isLast ? script.totalChars : script.offsets[i + 1]

    result.push({
      text: text.slice(0, shown),
      tone,
      cursor:
        partial ||
        (chars < script.totalChars && shown === text.length && chars <= nextStart),
    })

    if (partial) break
  }

  return result
}

/** 0-100 的整数进度百分比，chars 超界时钳位到 100。 */
export function computeProgressPercent(
  script: CompiledStreamScript,
  chars: number
): number {
  if (script.totalChars <= 0) return 0
  return Math.min(100, Math.round((chars / script.totalChars) * 100))
}

/** 是否已流完全部字符(analyzing 阶段据此切到「完成」态)。 */
export function isStreamDone(
  script: CompiledStreamScript,
  chars: number
): boolean {
  return chars >= script.totalChars
}

export type TrackRowStatus = '完成' | '进行中' | '等待'

export interface StreamTrackRow {
  label: string
  status: TrackRowStatus
}

const CATEGORY_TRACK_LABEL: Record<EiaCategory, string> = {
  water: '水类要素分析',
  soil: '土类要素分析',
  air: '气类要素分析',
  noise: '声类要素分析',
}

/** 左侧分轨进度：载入校验 → 各已激活类别 → 汇总编制，按 chars 推进标记 完成/进行中/等待。 */
export function buildTrackRows(
  script: CompiledStreamScript,
  chars: number
): StreamTrackRow[] {
  const checkpoints = [
    { label: '载入与完整性校验', start: 0 },
    ...script.activeCategories.map((category) => ({
      label: CATEGORY_TRACK_LABEL[category],
      start: script.offsets[script.catStart[category] ?? 0],
    })),
    { label: '汇总编制报告', start: script.offsets[script.tailStart] ?? 0 },
  ]

  return checkpoints.map((checkpoint, index) => {
    const nextStart =
      index < checkpoints.length - 1
        ? checkpoints[index + 1].start
        : script.totalChars
    const done = chars >= nextStart
    const running = !done && chars > checkpoint.start

    return {
      label: checkpoint.label,
      status: done ? '完成' : running ? '进行中' : '等待',
    }
  })
}
