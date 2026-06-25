import {
  type SysFile,
  type SysFilePage,
  type SysFileQuery,
  normalizeSysFile,
} from './model'

const localFiles = [
  {
    id: '1',
    originalName: '系统菜单说明.pdf',
    storageName: 'system-menu-guide.pdf',
    filePath: '/local/system-menu-guide.pdf',
    url: null,
    size: 245760,
    extension: 'pdf',
    contentType: 'application/pdf',
    md5: null,
    storageType: 'local-json',
    bucket: null,
    bizType: 'attachment',
    bizId: 'system',
    uploadBy: '1',
    uploadTime: '2026-06-25 00:00:00',
    createTime: '2026-06-25 00:00:00',
  },
].map(normalizeSysFile)

function paginate(records: SysFile[], query: SysFileQuery): SysFilePage {
  const pageNum = Math.max(query.pageNum, 1)
  const pageSize = Math.max(query.pageSize, 1)
  const start = (pageNum - 1) * pageSize

  return {
    pageNum,
    pageSize,
    total: records.length,
    pages: Math.max(Math.ceil(records.length / pageSize), 1),
    records: records.slice(start, start + pageSize),
  }
}

export async function fetchFilePage(query: SysFileQuery): Promise<SysFilePage> {
  const records = localFiles.filter(
    (file) =>
      (!query.originalName?.trim() ||
        file.originalName.includes(query.originalName)) &&
      (!query.extension?.trim() || file.extension.includes(query.extension)) &&
      (!query.bizType?.trim() || file.bizType === query.bizType) &&
      (!query.uploadBy?.trim() || file.uploadBy === query.uploadBy)
  )

  return paginate(records, query)
}

export async function fetchFileDetail(id: string): Promise<SysFile> {
  return localFiles.find((file) => file.id === id) ?? localFiles[0]
}

export type UploadFileParams = {
  file: File
  bizType?: string
  bizId?: string
  path?: string
  onProgress?: (percent: number) => void
}

export async function uploadFile(params: UploadFileParams): Promise<SysFile> {
  params.onProgress?.(100)
  return normalizeSysFile({
    id: String(localFiles.length + 1),
    originalName: params.file.name,
    storageName: params.file.name,
    filePath: params.path || '/local',
    size: params.file.size,
    extension: params.file.name.split('.').pop() ?? '',
    contentType: params.file.type || null,
    storageType: 'local-json',
    bizType: params.bizType ?? null,
    bizId: params.bizId ?? null,
    uploadBy: '1',
    uploadTime: new Date().toLocaleString('zh-CN', { hour12: false }),
    createTime: new Date().toLocaleString('zh-CN', { hour12: false }),
  })
}

export async function deleteFiles(ids: string[]): Promise<number> {
  return ids.length
}

export function getDownloadUrl(id: string) {
  return `local-json://${id}/download`
}

export function getPreviewUrl(id: string) {
  return `local-json://${id}/preview`
}

export async function fetchBlob(
  id: string,
  endpoint: 'download' | 'preview' = 'download'
): Promise<Blob> {
  return new Blob([`local json ${endpoint}: ${id}`], {
    type: 'text/plain;charset=utf-8',
  })
}
