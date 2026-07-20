import { describe, expect, test } from 'bun:test'
import type { OcrJobStatusResponse, OcrJobUnit } from '@/features/audit/types'
import {
  deriveOcrJobPhase,
  groupUnitsByFile,
  isTerminalJobStatus,
  OCR_JOB_POLL_INTERVAL_MS,
  ocrJobRefetchInterval,
  unitDisplayText,
  unitErrorText,
} from './job-model'

function job(
  overrides: Partial<OcrJobStatusResponse> = {}
): OcrJobStatusResponse {
  return {
    request_id: 'req-1',
    status: 'running',
    progress: { done: 1, total: 2 },
    results: [],
    error_detail: null,
    ...overrides,
  }
}

describe('isTerminalJobStatus', () => {
  test('completed and failed are terminal', () => {
    expect(isTerminalJobStatus('completed')).toBe(true)
    expect(isTerminalJobStatus('failed')).toBe(true)
  })

  test('queued and running are not terminal', () => {
    expect(isTerminalJobStatus('queued')).toBe(false)
    expect(isTerminalJobStatus('running')).toBe(false)
  })
})

describe('ocrJobRefetchInterval', () => {
  test('polls before first response arrives (data undefined)', () => {
    expect(ocrJobRefetchInterval(undefined)).toBe(OCR_JOB_POLL_INTERVAL_MS)
  })

  test('stops polling when job lookup fails (data null, e.g. 404)', () => {
    expect(ocrJobRefetchInterval(null)).toBe(false)
  })

  test('keeps polling while queued or running', () => {
    expect(ocrJobRefetchInterval(job({ status: 'queued' }))).toBe(
      OCR_JOB_POLL_INTERVAL_MS
    )
    expect(ocrJobRefetchInterval(job({ status: 'running' }))).toBe(
      OCR_JOB_POLL_INTERVAL_MS
    )
  })

  test('stops polling on completed or failed', () => {
    expect(ocrJobRefetchInterval(job({ status: 'completed' }))).toBe(false)
    expect(ocrJobRefetchInterval(job({ status: 'failed' }))).toBe(false)
  })
})

describe('deriveOcrJobPhase', () => {
  test('submitting takes priority over everything else', () => {
    expect(
      deriveOcrJobPhase({ isSubmitting: true, jobId: 'req-1', jobData: job() })
    ).toBe('submitting')
  })

  test('idle when nothing submitted yet', () => {
    expect(
      deriveOcrJobPhase({
        isSubmitting: false,
        jobId: null,
        jobData: undefined,
      })
    ).toBe('idle')
  })

  test('queued while first poll has not resolved', () => {
    expect(
      deriveOcrJobPhase({
        isSubmitting: false,
        jobId: 'req-1',
        jobData: undefined,
      })
    ).toBe('queued')
  })

  test('failed when job lookup returns null (404 / lost task)', () => {
    expect(
      deriveOcrJobPhase({ isSubmitting: false, jobId: 'req-1', jobData: null })
    ).toBe('failed')
  })

  test('passes through the polled job status once data arrives', () => {
    expect(
      deriveOcrJobPhase({
        isSubmitting: false,
        jobId: 'req-1',
        jobData: job({ status: 'running' }),
      })
    ).toBe('running')
    expect(
      deriveOcrJobPhase({
        isSubmitting: false,
        jobId: 'req-1',
        jobData: job({ status: 'completed' }),
      })
    ).toBe('completed')
  })
})

describe('groupUnitsByFile', () => {
  test('groups units by file, preserving first-seen file order', () => {
    const units: OcrJobUnit[] = [
      { file: 'a.pdf', page: 1, status: 'ok', payload: {}, from_cache: false },
      {
        file: 'b.pdf',
        page: null,
        status: 'ok',
        payload: {},
        from_cache: false,
      },
      { file: 'a.pdf', page: 2, status: 'ok', payload: {}, from_cache: false },
    ]

    const groups = groupUnitsByFile(units)

    expect(groups.map((g) => g.file)).toEqual(['a.pdf', 'b.pdf'])
    expect(groups[0]?.units).toHaveLength(2)
    expect(groups[1]?.units).toHaveLength(1)
  })

  test('sorts page units ascending within a file, file-level (page=null) first', () => {
    const units: OcrJobUnit[] = [
      { file: 'a.pdf', page: 2, status: 'ok', payload: {}, from_cache: false },
      {
        file: 'a.pdf',
        page: null,
        status: 'ok',
        payload: {},
        from_cache: false,
      },
      { file: 'a.pdf', page: 1, status: 'ok', payload: {}, from_cache: false },
    ]

    const groups = groupUnitsByFile(units)

    expect(groups[0]?.units.map((u) => u.page)).toEqual([null, 1, 2])
  })

  test('empty input yields no groups (partial rendering before first unit arrives)', () => {
    expect(groupUnitsByFile([])).toEqual([])
  })
})

describe('unitDisplayText', () => {
  test('prefers payload.text (native pdf page)', () => {
    expect(unitDisplayText({ text: '第一页文字' })).toBe('第一页文字')
  })

  test('falls back to payload.markdown (ocr engine page)', () => {
    expect(unitDisplayText({ markdown: '# OCR 页' })).toBe('# OCR 页')
  })

  test('falls back to joined payload.blocks (file-level native result)', () => {
    expect(unitDisplayText({ blocks: ['块一', '块二'] })).toBe('块一\n\n块二')
  })

  test('returns empty string when nothing displayable is present', () => {
    expect(unitDisplayText({ kind: 'manual' })).toBe('')
  })
})

describe('unitErrorText', () => {
  test('extracts a string error message', () => {
    expect(unitErrorText({ error: '文件损坏' })).toBe('文件损坏')
  })

  test('returns null when there is no error field', () => {
    expect(unitErrorText({ text: 'ok' })).toBeNull()
  })

  test('returns null when error is not a string (defensive, never trust shape)', () => {
    expect(unitErrorText({ error: { code: 500 } })).toBeNull()
  })
})
