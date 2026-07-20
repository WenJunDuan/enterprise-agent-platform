import { describe, expect, test } from 'bun:test'
import type { FormFillResult, OcrExtractItem } from '@/features/audit/types'
import {
  createInitialFillState,
  createInitialOcrWorkbenchState,
  createInitialStreamState,
  ocrWorkbenchReducer,
} from './mode-state'
import type { OcrUploadFile } from './shared'

// 2026-07-20 用户拍板：不下线回填，改为「识别+回填」(模式 A) + 「流式识别」(模式 B) 双能力
// 并存、单个 Tabs 切换。这个 reducer 是驱动切换的实际生产逻辑（页面组件直接用它），故这里的
// 单测直接覆盖用户验收原话："切到 A 走 fill、切到 B 走 jobs、切换清状态"。

function uploadFile(overrides: Partial<OcrUploadFile> = {}): OcrUploadFile {
  return {
    id: 'file-1',
    name: 'a.pdf',
    size: 10,
    status: 'pending',
    ...overrides,
  }
}

const SAMPLE_ITEMS: OcrExtractItem[] = [
  { path: 'a.pdf', kind: 'pdf_text', route: 'native' },
]
const SAMPLE_FILL: FormFillResult = {
  fields: [],
  sub_tables: [],
  needs_review: false,
}

describe('createInitialOcrWorkbenchState', () => {
  test('defaults to fill mode with both slices blank', () => {
    const state = createInitialOcrWorkbenchState()
    expect(state.mode).toBe('fill')
    expect(state.fill).toEqual(createInitialFillState())
    expect(state.stream).toEqual(createInitialStreamState())
  })
})

describe('ocrWorkbenchReducer: switch_mode (清状态)', () => {
  test('switching fill -> stream resets the fill slice (被离开的一侧清空)', () => {
    const state = createInitialOcrWorkbenchState()
    const withFillData = ocrWorkbenchReducer(state, {
      type: 'fill/submit_success',
      items: SAMPLE_ITEMS,
      fill: SAMPLE_FILL,
    })
    expect(withFillData.fill.items).toEqual(SAMPLE_ITEMS)

    const switched = ocrWorkbenchReducer(withFillData, {
      type: 'switch_mode',
      mode: 'stream',
    })

    expect(switched.mode).toBe('stream')
    expect(switched.fill).toEqual(createInitialFillState())
    expect(switched.stream).toEqual(createInitialStreamState())
  })

  test('switching stream -> fill resets the stream slice, leaves fill slice alone', () => {
    const state = {
      ...createInitialOcrWorkbenchState(),
      mode: 'stream' as const,
    }
    const withStreamData = ocrWorkbenchReducer(state, {
      type: 'stream/submit_accepted',
      jobId: 'job-1',
    })
    expect(withStreamData.stream.jobId).toBe('job-1')

    const switched = ocrWorkbenchReducer(withStreamData, {
      type: 'switch_mode',
      mode: 'fill',
    })

    expect(switched.mode).toBe('fill')
    expect(switched.stream).toEqual(createInitialStreamState())
    expect(switched.fill).toEqual(createInitialFillState())
  })

  test('switching to the currently active mode is a no-op (same state reference)', () => {
    const state = createInitialOcrWorkbenchState()
    const result = ocrWorkbenchReducer(state, {
      type: 'switch_mode',
      mode: 'fill',
    })
    expect(result).toBe(state)
  })

  test('data does not bleed across a round trip: fill -> stream -> fill starts clean', () => {
    let state = createInitialOcrWorkbenchState()
    state = ocrWorkbenchReducer(state, {
      type: 'fill/submit_success',
      items: SAMPLE_ITEMS,
      fill: SAMPLE_FILL,
    })
    state = ocrWorkbenchReducer(state, { type: 'switch_mode', mode: 'stream' })
    state = ocrWorkbenchReducer(state, {
      type: 'stream/submit_accepted',
      jobId: 'job-1',
    })
    state = ocrWorkbenchReducer(state, { type: 'switch_mode', mode: 'fill' })

    expect(state.fill).toEqual(createInitialFillState())
    expect(state.stream).toEqual(createInitialStreamState())
  })
})

describe('ocrWorkbenchReducer: fill/* actions only touch the fill slice (走 fill)', () => {
  test('fill/add_files appends to fill.files, leaves stream.files untouched', () => {
    const state = createInitialOcrWorkbenchState()
    const next = ocrWorkbenchReducer(state, {
      type: 'fill/add_files',
      files: [uploadFile()],
    })
    expect(next.fill.files).toHaveLength(1)
    expect(next.stream.files).toHaveLength(0)
  })

  test('fill/remove_file removes by id from fill.files only', () => {
    const state = ocrWorkbenchReducer(createInitialOcrWorkbenchState(), {
      type: 'fill/add_files',
      files: [uploadFile({ id: 'a' }), uploadFile({ id: 'b' })],
    })
    const next = ocrWorkbenchReducer(state, {
      type: 'fill/remove_file',
      id: 'a',
    })
    expect(next.fill.files.map((f) => f.id)).toEqual(['b'])
  })

  test('fill/submit_start marks files recognizing and clears prior results/error', () => {
    let state = ocrWorkbenchReducer(createInitialOcrWorkbenchState(), {
      type: 'fill/add_files',
      files: [uploadFile()],
    })
    state = ocrWorkbenchReducer(state, {
      type: 'fill/submit_error',
      message: 'previous failure',
    })
    const next = ocrWorkbenchReducer(state, { type: 'fill/submit_start' })

    expect(next.fill.phase).toBe('recognizing')
    expect(next.fill.error).toBeNull()
    expect(next.fill.items).toEqual([])
    expect(next.fill.fill).toBeNull()
    expect(next.fill.files.every((f) => f.status === 'recognizing')).toBe(true)
  })

  test('fill/submit_success sets items/fill/phase=done and marks files done', () => {
    let state = ocrWorkbenchReducer(createInitialOcrWorkbenchState(), {
      type: 'fill/add_files',
      files: [uploadFile()],
    })
    state = ocrWorkbenchReducer(state, { type: 'fill/submit_start' })
    const next = ocrWorkbenchReducer(state, {
      type: 'fill/submit_success',
      items: SAMPLE_ITEMS,
      fill: SAMPLE_FILL,
    })

    expect(next.fill.phase).toBe('done')
    expect(next.fill.items).toEqual(SAMPLE_ITEMS)
    expect(next.fill.fill).toEqual(SAMPLE_FILL)
    expect(next.fill.files.every((f) => f.status === 'done')).toBe(true)
  })

  test('fill/submit_error sets phase=error, records message, marks files error', () => {
    const state = ocrWorkbenchReducer(createInitialOcrWorkbenchState(), {
      type: 'fill/add_files',
      files: [uploadFile()],
    })
    const next = ocrWorkbenchReducer(state, {
      type: 'fill/submit_error',
      message: '识别失败',
    })

    expect(next.fill.phase).toBe('error')
    expect(next.fill.error).toBe('识别失败')
    expect(next.fill.files.every((f) => f.status === 'error')).toBe(true)
  })

  test('fill/submit_validation_error sets error without touching files (no real files selected yet)', () => {
    const state = createInitialOcrWorkbenchState()
    const next = ocrWorkbenchReducer(state, {
      type: 'fill/submit_validation_error',
      message: '请先选择真实文件',
    })

    expect(next.fill.phase).toBe('error')
    expect(next.fill.error).toBe('请先选择真实文件')
    expect(next.fill.files).toEqual([])
  })

  test('fill/load_sample sets items/fill/files directly with phase=done', () => {
    const sampleFiles = [uploadFile({ status: 'done' })]
    const next = ocrWorkbenchReducer(createInitialOcrWorkbenchState(), {
      type: 'fill/load_sample',
      items: SAMPLE_ITEMS,
      fill: SAMPLE_FILL,
      files: sampleFiles,
    })

    expect(next.fill.phase).toBe('done')
    expect(next.fill.items).toEqual(SAMPLE_ITEMS)
    expect(next.fill.fill).toEqual(SAMPLE_FILL)
    expect(next.fill.files).toEqual(sampleFiles)
  })
})

describe('ocrWorkbenchReducer: stream/* actions only touch the stream slice (走 jobs)', () => {
  function streamState() {
    return { ...createInitialOcrWorkbenchState(), mode: 'stream' as const }
  }

  test('stream/add_files appends to stream.files, leaves fill.files untouched', () => {
    const next = ocrWorkbenchReducer(streamState(), {
      type: 'stream/add_files',
      files: [uploadFile()],
    })
    expect(next.stream.files).toHaveLength(1)
    expect(next.fill.files).toHaveLength(0)
  })

  test('stream/remove_file removes by id from stream.files only', () => {
    const state = ocrWorkbenchReducer(streamState(), {
      type: 'stream/add_files',
      files: [uploadFile({ id: 'a' }), uploadFile({ id: 'b' })],
    })
    const next = ocrWorkbenchReducer(state, {
      type: 'stream/remove_file',
      id: 'a',
    })
    expect(next.stream.files.map((f) => f.id)).toEqual(['b'])
  })

  test('stream/submit_start clears jobId/submitError and marks files recognizing', () => {
    let state = ocrWorkbenchReducer(streamState(), {
      type: 'stream/add_files',
      files: [uploadFile()],
    })
    state = ocrWorkbenchReducer(state, {
      type: 'stream/submit_error',
      message: 'boom',
    })
    const next = ocrWorkbenchReducer(state, { type: 'stream/submit_start' })

    expect(next.stream.jobId).toBeNull()
    expect(next.stream.submitError).toBeNull()
    expect(next.stream.files.every((f) => f.status === 'recognizing')).toBe(
      true
    )
  })

  test('stream/submit_accepted records the job id', () => {
    const next = ocrWorkbenchReducer(streamState(), {
      type: 'stream/submit_accepted',
      jobId: 'job-42',
    })
    expect(next.stream.jobId).toBe('job-42')
  })

  test('stream/submit_error records the message and marks files error', () => {
    const state = ocrWorkbenchReducer(streamState(), {
      type: 'stream/add_files',
      files: [uploadFile()],
    })
    const next = ocrWorkbenchReducer(state, {
      type: 'stream/submit_error',
      message: '提交失败',
    })
    expect(next.stream.submitError).toBe('提交失败')
    expect(next.stream.files.every((f) => f.status === 'error')).toBe(true)
  })

  test('stream/submit_validation_error sets submitError without touching files', () => {
    const next = ocrWorkbenchReducer(streamState(), {
      type: 'stream/submit_validation_error',
      message: '请先选择真实文件',
    })
    expect(next.stream.submitError).toBe('请先选择真实文件')
    expect(next.stream.files).toEqual([])
  })

  test('stream/mark_files syncs file status from job polling (e.g. completed/failed)', () => {
    const state = ocrWorkbenchReducer(streamState(), {
      type: 'stream/add_files',
      files: [uploadFile()],
    })
    const next = ocrWorkbenchReducer(state, {
      type: 'stream/mark_files',
      status: 'done',
    })
    expect(next.stream.files.every((f) => f.status === 'done')).toBe(true)
  })

  test('stream actions never mutate the fill slice', () => {
    let state = streamState()
    state = ocrWorkbenchReducer(state, {
      type: 'stream/add_files',
      files: [uploadFile()],
    })
    state = ocrWorkbenchReducer(state, { type: 'stream/submit_start' })
    state = ocrWorkbenchReducer(state, {
      type: 'stream/submit_accepted',
      jobId: 'job-1',
    })
    state = ocrWorkbenchReducer(state, {
      type: 'stream/mark_files',
      status: 'done',
    })

    expect(state.fill).toEqual(createInitialFillState())
  })
})
