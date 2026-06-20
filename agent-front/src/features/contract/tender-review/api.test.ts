import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import { persistTenantToken } from '@/features/audit/api'
import {
  createTenderProject,
  evaluateTenderProjectUpload,
  getTenderCompareOrNull,
  listTenderProjects,
} from './api'

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

describe('contract tender review api', () => {
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

  test('createTenderProject posts JSON with tenant authorization', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({
        project_id: 'project-1',
        tender_no: 'WX-2026-001',
        title: '无锡项目',
        status: 'doing',
        created_at: '2026-06-20T00:00:00+00:00',
        updated_at: '2026-06-20T00:00:00+00:00',
      })
    }) as typeof fetch

    const project = await createTenderProject({
      tender_no: 'WX-2026-001',
      title: '无锡项目',
      method: '综合评估法',
      funding_type: 'unknown',
    })

    expect(project.project_id).toBe('project-1')
    expect(calls[0]?.input).toBe('/tender/projects')
    expect(calls[0]?.init?.method).toBe('POST')
    expect(calls[0]?.init?.headers).toEqual({
      Authorization: 'Bearer tenant-token',
      'Content-Type': 'application/json',
    })
    expect(calls[0]?.init?.body).toBe(
      JSON.stringify({
        tender_no: 'WX-2026-001',
        title: '无锡项目',
        method: '综合评估法',
        funding_type: 'unknown',
      })
    )
  })

  test('listTenderProjects includes list query params', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse([])
    }) as typeof fetch

    await listTenderProjects({ status: 'done', limit: 50, offset: 10 })

    expect(calls[0]?.input).toBe('/tender/projects?status=done&limit=50&offset=10')
    expect(calls[0]?.init?.headers).toEqual({
      Authorization: 'Bearer tenant-token',
    })
  })

  test('evaluateTenderProjectUpload sends upload mode, form metadata, and all tender plus bidder files', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({
        request_id: 'req-1',
        status: 'accepted',
        mode: 'upload',
        task_status_url: '/tender/tasks/req-1',
      })
    }) as typeof fetch

    const tenderFile = new File(['tender'], '招标文件.pdf', {
      type: 'application/pdf',
    })
    const bidderFile = new File(['bid'], '投标文件.pdf', {
      type: 'application/pdf',
    })

    const accepted = await evaluateTenderProjectUpload('project-1', {
      bidderName: '中建一局',
      tenderFiles: [tenderFile],
      bidderFiles: [bidderFile],
    })

    expect(accepted.request_id).toBe('req-1')
    expect(calls[0]?.input).toBe('/tender/projects/project-1/evaluate')
    expect(calls[0]?.init?.method).toBe('POST')
    expect(calls[0]?.init?.headers).toEqual({
      Authorization: 'Bearer tenant-token',
    })
    const body = calls[0]?.init?.body
    expect(body).toBeInstanceOf(FormData)
    const form = body as FormData
    expect(form.get('mode')).toBe('upload')
    expect(JSON.parse(String(form.get('form_json')))).toMatchObject({
      bidder_name: '中建一局',
      tender_files: ['招标文件.pdf'],
      bidder_files: ['投标文件.pdf'],
    })
    expect(form.getAll('files').map((file) => (file as File).name)).toEqual([
      '招标文件.pdf',
      '投标文件.pdf',
    ])
  })

  test('getTenderCompareOrNull treats missing compare as null', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({ detail: '尚未生成横比结果，请先触发 compare' }, 404)
    }) as typeof fetch

    const compare = await getTenderCompareOrNull('project-1')

    expect(compare).toBeNull()
    expect(calls[0]?.input).toBe('/tender/projects/project-1/compare')
  })
})
