import { toId } from '@/lib/ids'

export type OnlineUser = {
  userId: string
  username: string
  nickname: string | null
  deptName: string | null
  tokenId: string
  loginIp: string | null
  loginLocation: string | null
  browser: string | null
  os: string | null
  loginTime: string | null
  lastAccessTime: string | null
}

export type OnlineOverview = {
  total: number
  departmentCount: number
  topBrowser: { label: string; value: number } | null
  topOs: { label: string; value: number } | null
}

export type OnlineUserFilters = {
  username: string
  nickname: string
  deptName: string
  loginIp: string
  loginLocation: string
  device: string
  tokenId: string
}

export const defaultOnlineUserFilters: OnlineUserFilters = {
  username: '',
  nickname: '',
  deptName: '',
  loginIp: '',
  loginLocation: '',
  device: '',
  tokenId: '',
}

function getRecord(input: unknown): Record<string, unknown> {
  return (input && typeof input === 'object' ? input : {}) as Record<
    string,
    unknown
  >
}

function toNullableString(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

function getTopStat(values: Array<string | null>) {
  const counter = new Map<string, number>()

  for (const value of values) {
    if (!value) continue
    counter.set(value, (counter.get(value) ?? 0) + 1)
  }

  const [label, value] = [...counter.entries()].sort((left, right) => {
    if (right[1] !== left[1]) {
      return right[1] - left[1]
    }
    return left[0].localeCompare(right[0], 'zh-CN')
  })[0] ?? [null, null]

  return label && value ? { label, value } : null
}

export function normalizeOnlineUser(input: unknown): OnlineUser {
  const record = getRecord(input)

  return {
    userId: toId(record.userId ?? record.id),
    username: String(record.username ?? ''),
    nickname: toNullableString(record.nickname),
    deptName: toNullableString(record.deptName),
    tokenId: toId(record.tokenId),
    loginIp: toNullableString(record.loginIp),
    loginLocation: toNullableString(record.loginLocation),
    browser: toNullableString(record.browser),
    os: toNullableString(record.os),
    loginTime: toNullableString(record.loginTime),
    lastAccessTime: toNullableString(record.lastAccessTime),
  }
}

export function buildOnlineOverview(users: OnlineUser[]): OnlineOverview {
  const deptNames = new Set(users.map((user) => user.deptName).filter(Boolean))

  return {
    total: users.length,
    departmentCount: deptNames.size,
    topBrowser: getTopStat(users.map((user) => user.browser)),
    topOs: getTopStat(users.map((user) => user.os)),
  }
}

function includesIgnoreCase(value: string | null, keyword: string) {
  if (!keyword) return true
  if (!value) return false
  return value.toLowerCase().includes(keyword.toLowerCase())
}

function normalizeOnlineUserFilters(filters: OnlineUserFilters): OnlineUserFilters {
  return {
    username: filters.username.trim(),
    nickname: filters.nickname.trim(),
    deptName: filters.deptName.trim(),
    loginIp: filters.loginIp.trim(),
    loginLocation: filters.loginLocation.trim(),
    device: filters.device.trim(),
    tokenId: filters.tokenId.trim(),
  }
}

export function hasOnlineUserFilters(filters: OnlineUserFilters) {
  return Object.values(normalizeOnlineUserFilters(filters)).some(Boolean)
}

export function filterOnlineUsers(
  users: OnlineUser[],
  filters: OnlineUserFilters
) {
  const normalizedFilters = normalizeOnlineUserFilters(filters)

  return users.filter((user) => {
    if (!includesIgnoreCase(user.username, normalizedFilters.username)) {
      return false
    }
    if (!includesIgnoreCase(user.nickname, normalizedFilters.nickname)) {
      return false
    }
    if (!includesIgnoreCase(user.deptName, normalizedFilters.deptName)) {
      return false
    }
    if (!includesIgnoreCase(user.loginIp, normalizedFilters.loginIp)) {
      return false
    }
    if (
      !includesIgnoreCase(user.loginLocation, normalizedFilters.loginLocation)
    ) {
      return false
    }
    if (normalizedFilters.device) {
      const device = [user.browser, user.os].filter(Boolean).join(' ')
      if (!includesIgnoreCase(device, normalizedFilters.device)) {
        return false
      }
    }
    if (!includesIgnoreCase(user.tokenId, normalizedFilters.tokenId)) {
      return false
    }
    return true
  })
}

export function formatDateTime(value: string | null) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}
