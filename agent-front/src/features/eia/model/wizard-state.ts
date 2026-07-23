import {
  EIA_CATEGORY_ORDER,
  type EiaCategory,
  type EiaFilesByCategory,
  type EiaUploadFile,
} from '../types'

// 提交向导三步(分类上传 → 确认提交 → AI 分析)的实际生产 reducer(submit-page.tsx 直接用它)。
// 仿 features/ocr/workbench/mode-state.ts 的 useReducer 纪律：单一 reducer 驱动整页状态，
// 单测直接对着它覆盖用户验收原话——首屏四类为空、三步跳转、加载示例、再提交清空。

export type EiaWizardStep = 1 | 2 | 3

export interface EiaWizardState {
  step: EiaWizardStep
  files: EiaFilesByCategory
  analyzing: boolean
  reportReady: boolean
  chars: number
}

export function createInitialEiaFiles(): EiaFilesByCategory {
  return { water: [], soil: [], air: [], noise: [] }
}

export function createInitialEiaWizardState(): EiaWizardState {
  return {
    step: 1,
    files: createInitialEiaFiles(),
    analyzing: false,
    reportReady: false,
    chars: 0,
  }
}

export type EiaWizardAction =
  | { type: 'add_files'; category: EiaCategory; files: EiaUploadFile[] }
  | { type: 'remove_file'; category: EiaCategory; id: string }
  | { type: 'to_step2' }
  | { type: 'back_step1' }
  | { type: 'start_analysis' }
  | { type: 'advance_chars'; chars: number }
  | { type: 'view_reports' }
  | { type: 'replay_analysis' }
  | { type: 'reset_wizard' }
  | { type: 'load_sample'; files: EiaFilesByCategory }

/** 已上传材料的类别（按 water/soil/air/noise 固定顺序，忽略空类别）。 */
export function getActiveCategories(files: EiaFilesByCategory): EiaCategory[] {
  return EIA_CATEGORY_ORDER.filter((category) => files[category].length > 0)
}

/** 四类合计文件数。 */
export function getTotalFileCount(files: EiaFilesByCategory): number {
  return EIA_CATEGORY_ORDER.reduce(
    (total, category) => total + files[category].length,
    0
  )
}

/** 第一步「下一步」按钮是否禁用：至少一个类别有材料才能进入确认页。 */
export function isStep1Blocked(files: EiaFilesByCategory): boolean {
  return getTotalFileCount(files) === 0
}

export function eiaWizardReducer(
  state: EiaWizardState,
  action: EiaWizardAction
): EiaWizardState {
  switch (action.type) {
    case 'add_files':
      return {
        ...state,
        files: {
          ...state.files,
          [action.category]: [
            ...state.files[action.category],
            ...action.files,
          ],
        },
      }
    case 'remove_file':
      return {
        ...state,
        files: {
          ...state.files,
          [action.category]: state.files[action.category].filter(
            (file) => file.id !== action.id
          ),
        },
      }
    case 'to_step2':
      return { ...state, step: 2 }
    case 'back_step1':
      return { ...state, step: 1 }
    case 'start_analysis':
      return {
        ...state,
        step: 3,
        analyzing: true,
        reportReady: false,
        chars: 0,
      }
    case 'advance_chars':
      return { ...state, chars: action.chars }
    case 'view_reports':
      return { ...state, analyzing: false, reportReady: true }
    case 'replay_analysis':
      return { ...state, analyzing: true, reportReady: false, chars: 0 }
    case 'reset_wizard':
      return createInitialEiaWizardState()
    case 'load_sample':
      return { ...state, files: action.files }
    default:
      return state
  }
}
