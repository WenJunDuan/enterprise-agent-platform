import { toId } from '@/lib/ids'

export type SysFile = {
  id: string
  originalName: string
  storageName: string
  filePath: string
  url: string | null
  size: number
  sizeFormatted: string
  extension: string
  contentType: string | null
  md5: string | null
  storageType: string
  bucket: string | null
  bizType: string | null
  bizId: string | null
  uploadBy: string | null
  uploadTime: string | null
  createTime: string | null
}

export type SysFileQuery = {
  pageNum: number
  pageSize: number
  originalName?: string
  extension?: string
  bizType?: string
  uploadBy?: string
  beginTime?: string
  endTime?: string
}

export type SysFilePage = {
  pageNum: number
  pageSize: number
  total: number
  pages: number
  records: SysFile[]
}

export const BIZ_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'other', label: '其它' },
  { value: 'avatar', label: '头像' },
  { value: 'attachment', label: '附件' },
  { value: 'talent_attachment', label: '人才附件' },
  { value: 'import', label: '导入' },
  { value: 'export', label: '导出' },
  { value: 'icon', label: '图标' },
]

export const PREVIEWABLE_EXTENSIONS = new Set([
  'jpg',
  'jpeg',
  'png',
  'gif',
  'webp',
  'bmp',
  'ico',
  'pdf',
])

export function formatFileSize(size: number) {
  if (!size && size !== 0) {
    return '-'
  }
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(2)} KB`
  }
  if (size < 1024 * 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(2)} MB`
  }
  return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function canPreview(extension: string | null | undefined) {
  if (!extension) return false
  return PREVIEWABLE_EXTENSIONS.has(extension.toLowerCase())
}

function getRecord(input: unknown): Record<string, unknown> {
  return (input && typeof input === 'object' ? input : {}) as Record<
    string,
    unknown
  >
}

function toNullableString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

export function normalizeSysFile(input: unknown): SysFile {
  const record = getRecord(input)
  const size = Number(record.size ?? 0)

  return {
    id: toId(record.id),
    originalName: String(record.originalName ?? ''),
    storageName: String(record.storageName ?? ''),
    filePath: String(record.filePath ?? ''),
    url: toNullableString(record.url),
    size,
    sizeFormatted: formatFileSize(size),
    extension: String(record.extension ?? '').toLowerCase(),
    contentType: toNullableString(record.contentType),
    md5: toNullableString(record.md5),
    storageType: String(record.storageType ?? 'local'),
    bucket: toNullableString(record.bucket),
    bizType: toNullableString(record.bizType),
    bizId:
      record.bizId === null || record.bizId === undefined
        ? null
        : toId(record.bizId),
    uploadBy:
      record.uploadBy === null || record.uploadBy === undefined
        ? null
        : toId(record.uploadBy),
    uploadTime: toNullableString(record.uploadTime),
    createTime: toNullableString(record.createTime),
  }
}
