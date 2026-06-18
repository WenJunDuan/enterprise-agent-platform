import { describe, expect, test } from 'bun:test'
import {
  buildOnlineOverview,
  filterOnlineUsers,
  formatDateTime,
  normalizeOnlineUser,
} from './model'

describe('online model', () => {
  test('normalizeOnlineUser should convert ids and trim nullable values', () => {
    const user = normalizeOnlineUser({
      userId: 1001,
      username: 'admin',
      nickname: '管理员',
      deptName: '平台研发',
      tokenId: '  token-1  ',
      loginIp: '127.0.0.1',
      loginLocation: '上海',
      browser: 'Chrome',
      os: 'macOS',
      loginTime: '2026-04-19T08:00:00',
      lastAccessTime: '',
    })

    expect(user.userId).toBe('1001')
    expect(user.tokenId).toBe('token-1')
    expect(user.lastAccessTime).toBeNull()
  })

  test('buildOnlineOverview should aggregate department, browser and os counts', () => {
    const overview = buildOnlineOverview([
      normalizeOnlineUser({
        userId: '1',
        username: 'admin',
        deptName: '平台研发',
        tokenId: 'token-1',
        browser: 'Chrome',
        os: 'macOS',
      }),
      normalizeOnlineUser({
        userId: '2',
        username: 'demo',
        deptName: '平台研发',
        tokenId: 'token-2',
        browser: 'Edge',
        os: 'Windows',
      }),
      normalizeOnlineUser({
        userId: '3',
        username: 'ops',
        deptName: '运维中心',
        tokenId: 'token-3',
        browser: 'Chrome',
        os: 'Windows',
      }),
    ])

    expect(overview.total).toBe(3)
    expect(overview.departmentCount).toBe(2)
    expect(overview.topBrowser?.label).toBe('Chrome')
    expect(overview.topBrowser?.value).toBe(2)
    expect(overview.topOs?.label).toBe('Windows')
    expect(overview.topOs?.value).toBe(2)
  })

  test('filterOnlineUsers should support combined field filters', () => {
    const users = [
      normalizeOnlineUser({
        userId: '1',
        username: 'admin',
        nickname: '管理员',
        deptName: '平台研发',
        tokenId: 'token-admin-1',
        loginIp: '10.0.0.1',
        loginLocation: '上海',
        browser: 'Chrome',
        os: 'macOS',
      }),
      normalizeOnlineUser({
        userId: '2',
        username: 'demo',
        nickname: '演示账号',
        deptName: '市场部',
        tokenId: 'token-demo-2',
        loginIp: '10.0.0.2',
        loginLocation: '北京',
        browser: 'Edge',
        os: 'Windows',
      }),
    ]

    expect(
      filterOnlineUsers(users, {
        username: 'adm',
        nickname: '管理',
        deptName: '研发',
        loginIp: '10.0.0.1',
        loginLocation: '上',
        device: 'chrome mac',
        tokenId: 'admin',
      }).map((user) => user.userId)
    ).toEqual(['1'])
  })

  test('filterOnlineUsers should ignore blank filters and exclude unmatched device filters', () => {
    const users = [
      normalizeOnlineUser({
        userId: '1',
        username: 'admin',
        tokenId: 'token-admin-1',
        browser: 'Chrome',
        os: 'macOS',
      }),
    ]

    expect(
      filterOnlineUsers(users, {
        username: '  ',
        nickname: '',
        deptName: '',
        loginIp: '',
        loginLocation: '',
        device: 'windows',
        tokenId: '',
      })
    ).toHaveLength(0)
  })

  test('formatDateTime should format ISO timestamp and fallback for empty values', () => {
    expect(formatDateTime('2026-04-19T08:00:00')).toBe('2026-04-19 08:00:00')
    expect(formatDateTime(null)).toBe('-')
  })
})
