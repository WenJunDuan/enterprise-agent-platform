import type {
  DictData,
  DictDataFormInput,
  DictDataListQuery,
  DictType,
  DictTypeFormInput,
  DictTypeListQuery,
  PagedResult,
} from './model'

const localDictTypes: DictType[] = [
  {
    id: '1',
    dictName: '系统状态',
    dictType: 'sys_normal_disable',
    status: 1,
    remark: '本地 JSON 数据',
    createTime: '2026-06-25 00:00:00',
  },
  {
    id: '2',
    dictName: '用户性别',
    dictType: 'sys_user_sex',
    status: 1,
    remark: '本地 JSON 数据',
    createTime: '2026-06-25 00:00:00',
  },
]

const localDictData: DictData[] = [
  {
    id: '1',
    dictType: 'sys_normal_disable',
    dictLabel: '正常',
    dictValue: '1',
    dictSort: 0,
    cssClass: null,
    listClass: 'success',
    isDefault: 'Y',
    status: 1,
    remark: null,
    createTime: '2026-06-25 00:00:00',
  },
  {
    id: '2',
    dictType: 'sys_normal_disable',
    dictLabel: '停用',
    dictValue: '0',
    dictSort: 1,
    cssClass: null,
    listClass: 'danger',
    isDefault: 'N',
    status: 1,
    remark: null,
    createTime: '2026-06-25 00:00:00',
  },
  {
    id: '3',
    dictType: 'sys_user_sex',
    dictLabel: '未知',
    dictValue: '0',
    dictSort: 0,
    cssClass: null,
    listClass: 'default',
    isDefault: 'Y',
    status: 1,
    remark: null,
    createTime: '2026-06-25 00:00:00',
  },
]

function toPage<T>(records: T[]): PagedResult<T> {
  return {
    pageNum: 1,
    pageSize: 2000,
    total: records.length,
    pages: 1,
    records,
  }
}

export async function fetchDictTypePage(query?: Partial<DictTypeListQuery>) {
  const records = localDictTypes.filter(
    (item) =>
      (!query?.dictName?.trim() || item.dictName.includes(query.dictName)) &&
      (!query?.dictType?.trim() || item.dictType.includes(query.dictType)) &&
      (query?.status === undefined || item.status === query.status)
  )

  return toPage(records)
}

export async function createDictType(_input: DictTypeFormInput) {
  return String(localDictTypes.length + 1)
}

export async function updateDictType(_input: DictTypeFormInput) {
  return null
}

export async function deleteDictTypes(_ids: string[]) {
  return null
}

export async function refreshDictCache() {
  return null
}

export async function fetchDictDataList(query: DictDataListQuery) {
  return localDictData.filter(
    (item) =>
      item.dictType === query.dictType &&
      (!query.dictLabel?.trim() || item.dictLabel.includes(query.dictLabel)) &&
      (query.status === undefined || item.status === query.status)
  )
}

export async function createDictData(_input: DictDataFormInput) {
  return String(localDictData.length + 1)
}

export async function updateDictData(_input: DictDataFormInput) {
  return null
}

export async function deleteDictData(_ids: string[]) {
  return null
}
