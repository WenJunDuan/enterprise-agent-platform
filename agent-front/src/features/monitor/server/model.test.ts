import { describe, expect, test } from 'bun:test'
import {
  buildServerOverview,
  normalizeServerInfo,
  toUsageChartData,
} from './model'

describe('server model', () => {
  test('normalizeServerInfo should keep nested metrics and default missing lists', () => {
    const server = normalizeServerInfo({
      cpu: {
        cpuNum: 8,
        total: 62.5,
        sys: 18.1,
        used: 24.4,
        wait: 0,
        free: 37.5,
      },
      mem: {
        total: '32 GB',
        used: '12 GB',
        free: '20 GB',
        usage: 37.5,
      },
      jvm: {
        name: 'OpenJDK',
        version: '25',
        home: '/java',
        total: '4 GB',
        max: '8 GB',
        used: '2 GB',
        free: '2 GB',
        usage: 50,
        startTime: '2026-04-19 09:00:00',
        runTime: '0天2小时10分钟',
      },
      sys: {
        computerName: 'prod-01',
        computerIp: '10.0.0.8',
        osName: 'macOS',
        osArch: 'arm64',
        userDir: '/srv/app',
      },
      sysFiles: [{ dirName: '/', usage: 66.3 }],
    })

    expect(server.cpu.cpuNum).toBe(8)
    expect(server.jvm.max).toBe('8 GB')
    expect(server.sysFiles).toHaveLength(1)
  })

  test('buildServerOverview should surface key top-level figures', () => {
    const server = normalizeServerInfo({
      cpu: { cpuNum: 8, total: 62.5 },
      mem: { usage: 37.5 },
      jvm: { usage: 50, runTime: '0天2小时10分钟' },
      sys: { osName: 'Linux' },
      sysFiles: [{ dirName: '/', usage: 66.3 }, { dirName: '/data', usage: 40 }],
    })

    const overview = buildServerOverview(server)
    expect(overview.cpuUsage).toBe(62.5)
    expect(overview.memoryUsage).toBe(37.5)
    expect(overview.jvmUsage).toBe(50)
    expect(overview.diskCount).toBe(2)
  })

  test('toUsageChartData should build chart friendly rows', () => {
    const server = normalizeServerInfo({
      cpu: { total: 62.5 },
      mem: { usage: 37.5 },
      jvm: { usage: 50 },
    })

    expect(toUsageChartData(server)).toEqual([
      { name: 'CPU', usage: 62.5 },
      { name: '内存', usage: 37.5 },
      { name: 'JVM', usage: 50 },
    ])
  })
})
