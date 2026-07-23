import { describe, expect, test } from 'bun:test'
import type { EiaUploadFile } from '../types'
import {
  createInitialEiaFiles,
  createInitialEiaWizardState,
  eiaWizardReducer,
  getActiveCategories,
  getTotalFileCount,
  isStep1Blocked,
} from './wizard-state'

// 2026-07-23 环评智检提交向导：三步 stepper(分类上传 → 确认提交 → AI 分析)驱动整页的实际
// 生产 reducer(submit-page.tsx 直接用它)。首屏四类均为空(critic R1-F3)，演示文件只经
// load_sample 注入，不预置在初始 state 里。

function uploadFile(overrides: Partial<EiaUploadFile> = {}): EiaUploadFile {
  return { id: 'f-1', name: 'a.pdf', size: 1024, ...overrides }
}

describe('createInitialEiaWizardState', () => {
  test('starts at step 1 with all four categories empty (首屏四类为空)', () => {
    const state = createInitialEiaWizardState()
    expect(state.step).toBe(1)
    expect(state.files).toEqual(createInitialEiaFiles())
    expect(state.analyzing).toBe(false)
    expect(state.reportReady).toBe(false)
    expect(state.chars).toBe(0)
  })
})

describe('isStep1Blocked / getActiveCategories / getTotalFileCount', () => {
  test('blocks step 1 when every category is empty', () => {
    expect(isStep1Blocked(createInitialEiaFiles())).toBe(true)
    expect(getActiveCategories(createInitialEiaFiles())).toEqual([])
    expect(getTotalFileCount(createInitialEiaFiles())).toBe(0)
  })

  test('unblocks once any single category has a file, counts active categories/files', () => {
    const state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'add_files',
      category: 'air',
      files: [uploadFile({ id: 'a' }), uploadFile({ id: 'b' })],
    })

    expect(isStep1Blocked(state.files)).toBe(false)
    expect(getActiveCategories(state.files)).toEqual(['air'])
    expect(getTotalFileCount(state.files)).toBe(2)
  })
})

describe('eiaWizardReducer: file management', () => {
  test('add_files appends only to the targeted category', () => {
    const state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'add_files',
      category: 'water',
      files: [uploadFile()],
    })

    expect(state.files.water).toHaveLength(1)
    expect(state.files.soil).toHaveLength(0)
  })

  test('remove_file removes by id from the targeted category only', () => {
    let state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'add_files',
      category: 'soil',
      files: [uploadFile({ id: 'a' }), uploadFile({ id: 'b' })],
    })
    state = eiaWizardReducer(state, {
      type: 'remove_file',
      category: 'soil',
      id: 'a',
    })

    expect(state.files.soil.map((file) => file.id)).toEqual(['b'])
  })
})

describe('eiaWizardReducer: 三步跳转 (toStep2 / backStep1)', () => {
  test('to_step2 advances the wizard to step 2', () => {
    const state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'to_step2',
    })
    expect(state.step).toBe(2)
  })

  test('back_step1 returns from step 2 to step 1 without touching files', () => {
    let state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'add_files',
      category: 'noise',
      files: [uploadFile()],
    })
    state = eiaWizardReducer(state, { type: 'to_step2' })
    state = eiaWizardReducer(state, { type: 'back_step1' })

    expect(state.step).toBe(1)
    expect(state.files.noise).toHaveLength(1)
  })
})

describe('eiaWizardReducer: analysis lifecycle', () => {
  test('start_analysis moves to step 3, resets chars/reportReady, marks analyzing', () => {
    let state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'to_step2',
    })
    state = eiaWizardReducer(state, { type: 'start_analysis' })

    expect(state.step).toBe(3)
    expect(state.analyzing).toBe(true)
    expect(state.reportReady).toBe(false)
    expect(state.chars).toBe(0)
  })

  test('advance_chars sets the streamed character count', () => {
    let state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'start_analysis',
    })
    state = eiaWizardReducer(state, { type: 'advance_chars', chars: 42 })
    expect(state.chars).toBe(42)
  })

  test('view_reports stops analyzing and marks the report ready', () => {
    let state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'start_analysis',
    })
    state = eiaWizardReducer(state, {
      type: 'advance_chars',
      chars: 999,
    })
    state = eiaWizardReducer(state, { type: 'view_reports' })

    expect(state.analyzing).toBe(false)
    expect(state.reportReady).toBe(true)
  })

  test('replay_analysis re-enters the streaming state from a completed report', () => {
    let state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'start_analysis',
    })
    state = eiaWizardReducer(state, { type: 'advance_chars', chars: 999 })
    state = eiaWizardReducer(state, { type: 'view_reports' })
    state = eiaWizardReducer(state, { type: 'replay_analysis' })

    expect(state.analyzing).toBe(true)
    expect(state.reportReady).toBe(false)
    expect(state.chars).toBe(0)
  })

  test('reset_wizard clears files and returns to the pristine step-1 state (再提交一份)', () => {
    let state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'add_files',
      category: 'water',
      files: [uploadFile()],
    })
    state = eiaWizardReducer(state, { type: 'to_step2' })
    state = eiaWizardReducer(state, { type: 'start_analysis' })
    state = eiaWizardReducer(state, { type: 'advance_chars', chars: 999 })
    state = eiaWizardReducer(state, { type: 'view_reports' })
    state = eiaWizardReducer(state, { type: 'reset_wizard' })

    expect(state).toEqual(createInitialEiaWizardState())
  })
})

describe('eiaWizardReducer: load_sample (加载示例, 不改动初始态)', () => {
  test('load_sample injects demo files without touching step/analysis flags', () => {
    const sampleFiles = {
      ...createInitialEiaFiles(),
      water: [uploadFile({ id: 'demo-1' })],
    }
    const state = eiaWizardReducer(createInitialEiaWizardState(), {
      type: 'load_sample',
      files: sampleFiles,
    })

    expect(state.files).toEqual(sampleFiles)
    expect(state.step).toBe(1)
  })
})
