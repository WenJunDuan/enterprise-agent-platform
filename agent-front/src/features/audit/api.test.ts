import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import { getOcrJob, persistTenantToken, submitOcrJob } from './api'

// D9 streaming-ocr T4: submitOcrJob / getOcrJob against the real backend contract
// (server/routes/ocr_jobs.py: POST /ocr/jobs → 202 {request_id,status,task_status_url};
// GET /ocr/jobs/{request_id} → {request_id,status,progress,results,error_detail}).
// Pattern mirrors contract/tender-review/api.test.ts (fetch mocking + fake tenant window).

type FetchCall = {
  input: RequestInfo | URL
  init?: RequestInit
}

const originalFetch = globalThis.fetch

function installTestWindow() {
  const storage = new Map<string, string>()
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
        removeItem: (key: string) => storage.delete(key),
      },
    },
  })
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('ocr job api', () => {
  let calls: FetchCall[]

  beforeEach(() => {
    calls = []
    installTestWindow()
    persistTenantToken('tenant-token')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    Reflect.deleteProperty(globalThis, 'window')
  })

  test('submitOcrJob posts multipart files and returns the accepted job', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse(
        {
          request_id: 'ocr-job-1',
          status: 'queued',
          task_status_url: '/ocr/jobs/ocr-job-1',
        },
        202
      )
    }) as typeof fetch

    const file = new File(['content'], 'a.txt', { type: 'text/plain' })
    const accepted = await submitOcrJob([file])

    expect(accepted.request_id).toBe('ocr-job-1')
    expect(accepted.status).toBe('queued')
    expect(calls[0]?.input).toBe('/ocr/jobs')
    expect(calls[0]?.init?.method).toBe('POST')
    expect(calls[0]?.init?.headers).toEqual({
      Authorization: 'Bearer tenant-token',
    })
    const body = calls[0]?.init?.body as FormData
    expect(body).toBeInstanceOf(FormData)
    expect(body.getAll('files').map((f) => (f as File).name)).toEqual(['a.txt'])
  })

  // 503 (OCR_JOB_QUEUE_FULL, server/routes/ocr_jobs.py admission_available() gate) is a
  // gateway-class status; handleResponse (audit/api.ts) intentionally overrides its body
  // detail with a generic retry message for all 502/503/504 — same shared behavior every
  // other endpoint in this file relies on, not something specific to jobs to re-derive.
  test('submitOcrJob surfaces a friendly retry message when the queue is full (503)', async () => {
    globalThis.fetch = (async () => {
      return jsonResponse({ detail: 'OCR 任务队列已满，请稍后重试' }, 503)
    }) as typeof fetch

    await expect(submitOcrJob([new File(['x'], 'a.txt')])).rejects.toThrow(
      '服务暂不可用，请稍后重试。'
    )
  })

  test('submitOcrJob surfaces the server error message on a non-gateway failure', async () => {
    globalThis.fetch = (async () => {
      return jsonResponse({ detail: '未选择任何文件' }, 400)
    }) as typeof fetch

    await expect(submitOcrJob([new File(['x'], 'a.txt')])).rejects.toThrow(
      '未选择任何文件'
    )
  })

  test('getOcrJob polls the status endpoint with tenant auth', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({
        request_id: 'ocr-job-1',
        status: 'running',
        progress: { done: 1, total: 2 },
        results: [
          {
            file: 'a.txt',
            page: null,
            status: 'ok',
            payload: { text: 'hi' },
            from_cache: false,
          },
        ],
        error_detail: null,
      })
    }) as typeof fetch

    const status = await getOcrJob('ocr-job-1')

    expect(calls[0]?.input).toBe('/ocr/jobs/ocr-job-1')
    expect(calls[0]?.init?.headers).toEqual({
      Authorization: 'Bearer tenant-token',
    })
    expect(status.status).toBe('running')
    expect(status.progress).toEqual({ done: 1, total: 2 })
    expect(status.results).toHaveLength(1)
  })

  test('getOcrJob rejects on unknown request_id (404)', async () => {
    globalThis.fetch = (async () => {
      return jsonResponse({ detail: 'OCR job not found' }, 404)
    }) as typeof fetch

    await expect(getOcrJob('does-not-exist')).rejects.toThrow(
      'OCR job not found'
    )
  })

  test('getOcrJob URL-encodes the request_id', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({
        request_id: 'weird id/1',
        status: 'queued',
        progress: null,
        results: [],
        error_detail: null,
      })
    }) as typeof fetch

    await getOcrJob('weird id/1')

    expect(calls[0]?.input).toBe('/ocr/jobs/weird%20id%2F1')
  })
})
