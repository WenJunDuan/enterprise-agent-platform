import { afterEach, beforeEach, describe, expect, test } from 'bun:test'
import { persistTenantToken } from '@/features/audit/api'
import {
  createTenderProject,
  deleteTenderTask,
  evaluateTenderProjectUpload,
  getTenderCompareOrNull,
  listTenderProjects,
  retryTenderTask,
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
        scenario: 'expert_assist',
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

  test('createTenderProject and listTenderProjects pass scenario', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse(
        String(input).includes('?')
          ? []
          : {
              project_id: 'project-self-check',
              scenario: 'bidder_self_check',
              title: '投标自查',
              status: 'doing',
              created_at: '2026-06-20T00:00:00+00:00',
              updated_at: '2026-06-20T00:00:00+00:00',
            }
      )
    }) as typeof fetch

    const project = await createTenderProject({
      scenario: 'bidder_self_check',
      title: '投标自查',
    })
    await listTenderProjects({ scenario: 'bidder_self_check', limit: 20 })

    expect(project.scenario).toBe('bidder_self_check')
    expect(JSON.parse(String(calls[0]?.init?.body)).scenario).toBe(
      'bidder_self_check'
    )
    expect(calls[1]?.input).toBe(
      '/tender/projects?scenario=bidder_self_check&limit=20'
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

  // A①: createTenderProject sends all 6 project fields in body
  test('createTenderProject sends all 6 project fields including tenderee, control_price, funding_type', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({
        project_id: 'project-2',
        tender_no: 'SH-2026-002',
        title: '上海地铁项目',
        tenderee: '上海地铁集团',
        method: '最低投标价法',
        control_price: '50000000',
        funding_type: 'state_funded',
        status: 'doing',
        created_at: '2026-06-20T00:00:00+00:00',
        updated_at: '2026-06-20T00:00:00+00:00',
      })
    }) as typeof fetch

    const project = await createTenderProject({
      tender_no: 'SH-2026-002',
      title: '上海地铁项目',
      tenderee: '上海地铁集团',
      method: '最低投标价法',
      control_price: '50000000',
      funding_type: 'state_funded',
    })

    expect(project.project_id).toBe('project-2')
    const sentBody = JSON.parse(String(calls[0]?.init?.body))
    expect(sentBody.tender_no).toBe('SH-2026-002')
    expect(sentBody.title).toBe('上海地铁项目')
    expect(sentBody.tenderee).toBe('上海地铁集团')
    expect(sentBody.method).toBe('最低投标价法')
    expect(sentBody.control_price).toBe('50000000')
    expect(sentBody.funding_type).toBe('state_funded')
  })

  // B⑤: batch delete — calls DELETE /tender/tasks/{request_id} for each selected item
  test('deleteTenderTask calls DELETE /tender/tasks/{request_id}', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return new Response(null, { status: 204 })
    }) as typeof fetch

    await deleteTenderTask('req-abc')

    expect(calls[0]?.input).toBe('/tender/tasks/req-abc')
    expect(calls[0]?.init?.method).toBe('DELETE')
    expect(calls[0]?.init?.headers).toEqual({
      Authorization: 'Bearer tenant-token',
    })
  })

  test('batch delete calls deleteTenderTask for each selected request_id in order', async () => {
    const selectedIds = ['req-1', 'req-2', 'req-3']
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return new Response(null, { status: 204 })
    }) as typeof fetch

    for (const id of selectedIds) {
      await deleteTenderTask(id)
    }

    expect(calls).toHaveLength(3)
    expect(calls.map((call) => call.input)).toEqual([
      '/tender/tasks/req-1',
      '/tender/tasks/req-2',
      '/tender/tasks/req-3',
    ])
    expect(calls.every((call) => call.init?.method === 'DELETE')).toBe(true)
  })

  // B⑤: batch retry — calls POST /tender/tasks/{request_id}/retry for each selected item
  test('retryTenderTask calls POST /tender/tasks/{request_id}/retry', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({
        request_id: 'req-abc',
        status: 'accepted',
        mode: 'upload',
        updated_at: '2026-06-20T00:00:00+00:00',
      })
    }) as typeof fetch

    const result = await retryTenderTask('req-abc')

    expect(calls[0]?.input).toBe('/tender/tasks/req-abc/retry')
    expect(calls[0]?.init?.method).toBe('POST')
    expect(result.request_id).toBe('req-abc')
  })

  test('batch retry calls retryTenderTask for each selected request_id in order', async () => {
    const selectedIds = ['req-x', 'req-y']
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({
        request_id: String(input).split('/tasks/')[1]?.replace('/retry', '') ?? 'req-x',
        status: 'accepted',
        mode: 'upload',
        updated_at: '2026-06-20T00:00:00+00:00',
      })
    }) as typeof fetch

    for (const id of selectedIds) {
      await retryTenderTask(id)
    }

    expect(calls).toHaveLength(2)
    expect(calls.map((call) => call.input)).toEqual([
      '/tender/tasks/req-x/retry',
      '/tender/tasks/req-y/retry',
    ])
    expect(calls.every((call) => call.init?.method === 'POST')).toBe(true)
  })

  // E②: getTenderCompareOrNull does not throw on 404 — returns null silently (no console error)
  test('getTenderCompareOrNull does not throw on 404 and returns null silently', async () => {
    globalThis.fetch = (async () => {
      return jsonResponse({ detail: '横比未就绪' }, 404)
    }) as typeof fetch

    let thrownError: unknown = null
    let result: unknown = 'NOT_SET'
    try {
      result = await getTenderCompareOrNull('project-single-bidder')
    } catch (error) {
      thrownError = error
    }

    expect(thrownError).toBeNull()
    expect(result).toBeNull()
  })

  // B⑥: evaluateTenderProjectUpload for append-bidder to existing project
  test('evaluateTenderProjectUpload for appending a new bidder sends mode=upload with bidder files', async () => {
    globalThis.fetch = (async (input, init) => {
      calls.push({ input, init })
      return jsonResponse({
        request_id: 'req-append',
        status: 'accepted',
        mode: 'upload',
        task_status_url: '/tender/tasks/req-append',
      })
    }) as typeof fetch

    const bidderFile = new File(['data'], '投标附件.pdf', { type: 'application/pdf' })
    const tenderFile = new File(['tender'], '招标文件.pdf', { type: 'application/pdf' })

    const result = await evaluateTenderProjectUpload('project-99', {
      bidderName: '中铁五局',
      tenderFiles: [tenderFile],
      bidderFiles: [bidderFile],
    })

    expect(result.request_id).toBe('req-append')
    expect(calls[0]?.input).toBe('/tender/projects/project-99/evaluate')
    expect(calls[0]?.init?.method).toBe('POST')
    const body = calls[0]?.init?.body as FormData
    expect(body.get('mode')).toBe('upload')
    expect(JSON.parse(String(body.get('form_json')))).toMatchObject({
      bidder_name: '中铁五局',
    })
  })
})
