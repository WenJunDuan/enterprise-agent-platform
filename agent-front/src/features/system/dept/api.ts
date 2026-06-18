import type { ApiResult } from '@/types/api';
import { toId } from '@/lib/ids'
import { apiClient } from '@/lib/http';
import { buildDeptCreatePayload, buildDeptListQuery, buildDeptUpdatePayload, dedupeDeptTreeRoots, type DeptDetail, type DeptFormInput, type DeptListSearch, type DeptTreeNode } from './model';


function unwrapResult<T>(result: ApiResult<T>) {
  return result.data
}

function getRecord(input: unknown) {
  return (input && typeof input === 'object' ? input : {}) as Record<
    string,
    unknown
  >
}

function normalizeDeptTreeNode(input: unknown): DeptTreeNode {
  const record = getRecord(input)
  const children = Array.isArray(record.children)
    ? record.children.map(normalizeDeptTreeNode)
    : []
  const deptId = toId(record.deptId ?? record.id) || '0'
  const parentId = toId(record.parentId) || '0'

  return {
    deptId,
    parentId,
    deptName: String(record.deptName ?? record.label ?? ''),
    orderNum:
      record.orderNum === null || record.orderNum === undefined
        ? null
        : Number(record.orderNum),
    leader: typeof record.leader === 'string' ? record.leader : null,
    phone: typeof record.phone === 'string' ? record.phone : null,
    email: typeof record.email === 'string' ? record.email : null,
    status: Number(record.status ?? 1) === 0 ? 0 : 1,
    createTime:
      typeof record.createTime === 'string' ? record.createTime : null,
    children,
  }
}

export async function fetchDeptList(search?: Partial<DeptListSearch>) {
  const response = await apiClient.get<ApiResult<DeptTreeNode[]>>(
    '/system/dept/list',
    {
      params: buildDeptListQuery(search),
    }
  )

  return dedupeDeptTreeRoots(unwrapResult(response.data).map(normalizeDeptTreeNode))
}

export async function fetchDeptDetail(deptId: string) {
  const response = await apiClient.get<ApiResult<DeptDetail>>(
    `/system/dept/${deptId}`
  )

  return normalizeDeptTreeNode(unwrapResult(response.data))
}

export async function createDept(input: DeptFormInput) {
  const response = await apiClient.post<ApiResult<string | number>>(
    '/system/dept',
    buildDeptCreatePayload(input)
  )

  return toId(unwrapResult(response.data))
}

export async function updateDept(input: DeptFormInput, id: string) {
  const response = await apiClient.put<ApiResult<null>>(
    '/system/dept',
    buildDeptUpdatePayload(input, id)
  )

  return unwrapResult(response.data)
}

export async function deleteDept(id: string) {
  const response = await apiClient.delete<ApiResult<null>>(`/system/dept/${id}`)

  return unwrapResult(response.data)
}
