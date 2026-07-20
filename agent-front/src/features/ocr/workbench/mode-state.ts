import type { FormFillResult, OcrExtractItem } from '@/features/audit/types'
import type { OcrFileStatus, OcrUploadFile, RecognizePhase } from './shared'

// 2026-07-20 用户拍板：不下线回填，改为「识别+回填」(模式 A，同步 /ocr/fill) + 「流式识别」
// (模式 B，/ocr/jobs 轮询) 双能力并存，单个 Tabs 切换。这个 reducer 是驱动整页两种模式的实际
// 生产逻辑（ocr-workbench-page.tsx 直接用它），不是为了测试另起的影子实现——单测直接对着它
// 覆盖用户验收原话："切到 A 走 fill、切到 B 走 jobs、切换清状态"。

export type OcrWorkbenchMode = 'fill' | 'stream'

export interface FillModeState {
  files: OcrUploadFile[]
  items: OcrExtractItem[]
  fill: FormFillResult | null
  phase: RecognizePhase
  error: string | null
}

export interface StreamModeState {
  files: OcrUploadFile[]
  jobId: string | null
  submitError: string | null
}

export interface OcrWorkbenchState {
  mode: OcrWorkbenchMode
  fill: FillModeState
  stream: StreamModeState
}

export function createInitialFillState(): FillModeState {
  return { files: [], items: [], fill: null, phase: 'idle', error: null }
}

export function createInitialStreamState(): StreamModeState {
  return { files: [], jobId: null, submitError: null }
}

export function createInitialOcrWorkbenchState(): OcrWorkbenchState {
  return {
    mode: 'fill',
    fill: createInitialFillState(),
    stream: createInitialStreamState(),
  }
}

export type OcrWorkbenchAction =
  | { type: 'switch_mode'; mode: OcrWorkbenchMode }
  | { type: 'fill/add_files'; files: OcrUploadFile[] }
  | { type: 'fill/remove_file'; id: string }
  | { type: 'fill/submit_start' }
  | {
      type: 'fill/submit_success'
      items: OcrExtractItem[]
      fill: FormFillResult
    }
  | { type: 'fill/submit_error'; message: string }
  | { type: 'fill/submit_validation_error'; message: string }
  | {
      type: 'fill/load_sample'
      items: OcrExtractItem[]
      fill: FormFillResult
      files: OcrUploadFile[]
    }
  | { type: 'stream/add_files'; files: OcrUploadFile[] }
  | { type: 'stream/remove_file'; id: string }
  | { type: 'stream/submit_start' }
  | { type: 'stream/submit_accepted'; jobId: string }
  | { type: 'stream/submit_error'; message: string }
  | { type: 'stream/submit_validation_error'; message: string }
  | { type: 'stream/mark_files'; status: OcrFileStatus }

function markFiles(
  files: OcrUploadFile[],
  status: OcrFileStatus
): OcrUploadFile[] {
  return files.map((file) => ({ ...file, status }))
}

/**
 * 单一 reducer 驱动整页两种模式：模式切换时清理**被离开**那一侧的状态（回到初始态），保证两
 * 模式各自独立、不串数据；提交/结果落地按 `fill/*`、`stream/*` action 前缀严格隔离到各自 slice。
 */
export function ocrWorkbenchReducer(
  state: OcrWorkbenchState,
  action: OcrWorkbenchAction
): OcrWorkbenchState {
  switch (action.type) {
    case 'switch_mode': {
      if (action.mode === state.mode) return state
      return {
        mode: action.mode,
        fill: action.mode === 'stream' ? createInitialFillState() : state.fill,
        stream:
          action.mode === 'fill' ? createInitialStreamState() : state.stream,
      }
    }
    case 'fill/add_files':
      return {
        ...state,
        fill: { ...state.fill, files: [...state.fill.files, ...action.files] },
      }
    case 'fill/remove_file':
      return {
        ...state,
        fill: {
          ...state.fill,
          files: state.fill.files.filter((file) => file.id !== action.id),
        },
      }
    case 'fill/submit_start':
      return {
        ...state,
        fill: {
          ...state.fill,
          phase: 'recognizing',
          error: null,
          items: [],
          fill: null,
          files: markFiles(state.fill.files, 'recognizing'),
        },
      }
    case 'fill/submit_success':
      return {
        ...state,
        fill: {
          ...state.fill,
          phase: 'done',
          items: action.items,
          fill: action.fill,
          files: markFiles(state.fill.files, 'done'),
        },
      }
    case 'fill/submit_error':
      return {
        ...state,
        fill: {
          ...state.fill,
          phase: 'error',
          error: action.message,
          files: markFiles(state.fill.files, 'error'),
        },
      }
    case 'fill/submit_validation_error':
      // 未选真实文件即点提交：只报错，不动 files（原逻辑一致，files 本就不含真实文件可标记）。
      return {
        ...state,
        fill: { ...state.fill, phase: 'error', error: action.message },
      }
    case 'fill/load_sample':
      return {
        ...state,
        fill: {
          phase: 'done',
          error: null,
          items: action.items,
          fill: action.fill,
          files: action.files,
        },
      }
    case 'stream/add_files':
      return {
        ...state,
        stream: {
          ...state.stream,
          files: [...state.stream.files, ...action.files],
        },
      }
    case 'stream/remove_file':
      return {
        ...state,
        stream: {
          ...state.stream,
          files: state.stream.files.filter((file) => file.id !== action.id),
        },
      }
    case 'stream/submit_start':
      return {
        ...state,
        stream: {
          ...state.stream,
          submitError: null,
          jobId: null,
          files: markFiles(state.stream.files, 'recognizing'),
        },
      }
    case 'stream/submit_accepted':
      return { ...state, stream: { ...state.stream, jobId: action.jobId } }
    case 'stream/submit_error':
      return {
        ...state,
        stream: {
          ...state.stream,
          submitError: action.message,
          files: markFiles(state.stream.files, 'error'),
        },
      }
    case 'stream/submit_validation_error':
      return {
        ...state,
        stream: { ...state.stream, submitError: action.message },
      }
    case 'stream/mark_files':
      return {
        ...state,
        stream: {
          ...state.stream,
          files: markFiles(state.stream.files, action.status),
        },
      }
    default:
      return state
  }
}
