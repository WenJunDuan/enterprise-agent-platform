import type { ApiResult } from '@/types/api'
import { toId } from '@/lib/ids'
import { apiClient } from '@/lib/http'
import {
  buildDictDataPayload,
  buildDictTypePayload,
  type DictData,
  type DictDataFormInput,
  type DictDataListQuery,
  type DictDefaultFlag,
  type DictStatus,
  type DictType,
  type DictTypeFormInput,
  type DictTypeListQuery,
  type PagedResult,
} from './model'

function unwrapResult<T>(result: ApiResult<T>) {
  return result.data
}

function getRecord(input: unknown) {
  return (input && typeof input === 'object' ? input : {}) as Record<
    string,
    unknown
  >
}

function toNullableText(value: unknown) {
  if (typeof value !== 'string') {
    return null
  }

  const normalized = value.trim()
  return normalized === '' ? null : normalized
}

function normalizeStatus(value: unknown): DictStatus {
  return Number(value) === 0 ? 0 : 1
}

function normalizeDefaultFlag(value: unknown): DictDefaultFlag {
  return value === 'Y' ? 'Y' : 'N'
}

function normalizeDictType(input: unknown): DictType {
  const record = getRecord(input)
  return {
    id: toId(record.id),
    dictName: String(record.dictName ?? ''),
    dictType: String(record.dictType ?? ''),
    status: normalizeStatus(record.status),
    remark: toNullableText(record.remark),
    createTime: toNullableText(record.createTime),
  }
}

function normalizeDictData(input: unknown): DictData {
  const record = getRecord(input)
  return {
    id: toId(record.id),
    dictType: String(record.dictType ?? ''),
    dictLabel: String(record.dictLabel ?? ''),
    dictValue: String(record.dictValue ?? ''),
    dictSort: Number(record.dictSort ?? 0),
    cssClass: toNullableText(record.cssClass),
    listClass: toNullableText(record.listClass),
    isDefault: normalizeDefaultFlag(record.isDefault),
    status: normalizeStatus(record.status),
    remark: toNullableText(record.remark),
    createTime: toNullableText(record.createTime),
  }
}

export async function fetchDictTypePage(query?: Partial<DictTypeListQuery>) {
  const response = await apiClient.get<ApiResult<PagedResult<unknown>>>(
    '/system/dict/type/list',
    {
      params: {
        pageNum: 1,
        pageSize: 2000,
        dictName: query?.dictName?.trim() || undefined,
        dictType: query?.dictType?.trim() || undefined,
        status: query?.status,
      },
    }
  )

  const page = unwrapResult(response.data)
  return {
    pageNum: Number(page.pageNum ?? 1),
    pageSize: Number(page.pageSize ?? 2000),
    total: Number(page.total ?? 0),
    pages: Number(page.pages ?? 0),
    records: (page.records ?? []).map(normalizeDictType),
  } satisfies PagedResult<DictType>
}

export async function createDictType(input: DictTypeFormInput) {
  const response = await apiClient.post<ApiResult<number | string>>(
    '/system/dict/type',
    buildDictTypePayload(input)
  )

  return toId(unwrapResult(response.data))
}

export async function updateDictType(input: DictTypeFormInput) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/dict/type',
    buildDictTypePayload(input)
  )

  return unwrapResult(response.data)
}

export async function deleteDictTypes(ids: string[]) {
  const response = await apiClient.delete<ApiResult<null>>(
    `/system/dict/type/${ids.join(',')}`
  )

  return unwrapResult(response.data)
}

export async function refreshDictCache() {
  const response = await apiClient.delete<ApiResult<null>>(
    '/system/dict/type/refreshCache'
  )

  return unwrapResult(response.data)
}

export async function fetchDictDataList(query: DictDataListQuery) {
  const response = await apiClient.get<ApiResult<unknown[]>>(
    '/system/dict/data/list',
    {
      params: {
        dictType: query.dictType,
        dictLabel: query.dictLabel?.trim() || undefined,
        status: query.status,
      },
    }
  )

  return unwrapResult(response.data).map(normalizeDictData)
}

export async function createDictData(input: DictDataFormInput) {
  const response = await apiClient.post<ApiResult<number | string>>(
    '/system/dict/data',
    buildDictDataPayload(input)
  )

  return toId(unwrapResult(response.data))
}

export async function updateDictData(input: DictDataFormInput) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/dict/data',
    buildDictDataPayload(input)
  )

  return unwrapResult(response.data)
}

export async function deleteDictData(ids: string[]) {
  const response = await apiClient.delete<ApiResult<null>>(
    `/system/dict/data/${ids.join(',')}`
  )

  return unwrapResult(response.data)
}
