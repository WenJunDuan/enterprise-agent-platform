export type ServerInfo = {
  cpu: {
    cpuNum: number
    total: number
    sys: number
    used: number
    wait: number
    free: number
  }
  mem: {
    total: string
    used: string
    free: string
    usage: number
  }
  jvm: {
    name: string
    version: string
    home: string
    total: string
    max: string
    used: string
    free: string
    usage: number
    startTime: string
    runTime: string
  }
  sys: {
    computerName: string
    computerIp: string
    osName: string
    osArch: string
    userDir: string
  }
  sysFiles: Array<{
    dirName: string
    sysTypeName: string
    typeName: string
    total: string
    free: string
    used: string
    usage: number
  }>
}

export type ServerOverview = {
  cpuUsage: number
  memoryUsage: number
  jvmUsage: number
  diskCount: number
  runtime: string
  osName: string
}

function getRecord(input: unknown): Record<string, unknown> {
  return (input && typeof input === 'object' ? input : {}) as Record<
    string,
    unknown
  >
}

function toNumber(value: unknown) {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

function toStringValue(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function getUsageValue(value: unknown) {
  return Number(toNumber(value).toFixed(2))
}

export function normalizeServerInfo(input: unknown): ServerInfo {
  const record = getRecord(input)
  const cpu = getRecord(record.cpu)
  const mem = getRecord(record.mem)
  const jvm = getRecord(record.jvm)
  const sys = getRecord(record.sys)
  const rawSysFiles = Array.isArray(record.sysFiles) ? record.sysFiles : []

  return {
    cpu: {
      cpuNum: toNumber(cpu.cpuNum),
      total: getUsageValue(cpu.total),
      sys: getUsageValue(cpu.sys),
      used: getUsageValue(cpu.used),
      wait: getUsageValue(cpu.wait),
      free: getUsageValue(cpu.free),
    },
    mem: {
      total: toStringValue(mem.total),
      used: toStringValue(mem.used),
      free: toStringValue(mem.free),
      usage: getUsageValue(mem.usage),
    },
    jvm: {
      name: toStringValue(jvm.name),
      version: toStringValue(jvm.version),
      home: toStringValue(jvm.home),
      total: toStringValue(jvm.total),
      max: toStringValue(jvm.max),
      used: toStringValue(jvm.used),
      free: toStringValue(jvm.free),
      usage: getUsageValue(jvm.usage),
      startTime: toStringValue(jvm.startTime),
      runTime: toStringValue(jvm.runTime),
    },
    sys: {
      computerName: toStringValue(sys.computerName),
      computerIp: toStringValue(sys.computerIp),
      osName: toStringValue(sys.osName),
      osArch: toStringValue(sys.osArch),
      userDir: toStringValue(sys.userDir),
    },
    sysFiles: rawSysFiles.map((item) => {
      const sysFile = getRecord(item)
      return {
        dirName: toStringValue(sysFile.dirName),
        sysTypeName: toStringValue(sysFile.sysTypeName),
        typeName: toStringValue(sysFile.typeName),
        total: toStringValue(sysFile.total),
        free: toStringValue(sysFile.free),
        used: toStringValue(sysFile.used),
        usage: getUsageValue(sysFile.usage),
      }
    }),
  }
}

export function buildServerOverview(server: ServerInfo): ServerOverview {
  return {
    cpuUsage: server.cpu.total,
    memoryUsage: server.mem.usage,
    jvmUsage: server.jvm.usage,
    diskCount: server.sysFiles.length,
    runtime: server.jvm.runTime,
    osName: server.sys.osName,
  }
}

export function toUsageChartData(server: ServerInfo) {
  return [
    { name: 'CPU', usage: server.cpu.total },
    { name: '内存', usage: server.mem.usage },
    { name: 'JVM', usage: server.jvm.usage },
  ]
}
