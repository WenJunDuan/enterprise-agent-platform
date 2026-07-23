// 环评智检域类型 — 对齐 design.md A3。当前无后端(方案 C 已弃, 本期 mock-first),
// 这里的类型即未来 server/eia 接线时的契约起点(api.ts 单一接缝)。

export type EiaCategory = 'water' | 'soil' | 'air' | 'noise'

export const EIA_CATEGORY_ORDER: readonly EiaCategory[] = [
  'water',
  'soil',
  'air',
  'noise',
] as const

export interface EiaCategoryDef {
  key: EiaCategory
  glyph: string
  title: string
  hint: string
}

export interface EiaUploadFile {
  id: string
  name: string
  size: number
  /** 真实上传的文件对象;「加载示例」的演示项无此字段(mock 分析不读内容,交互仍走真实 File)。 */
  file?: File
}

export type EiaFilesByCategory = Record<EiaCategory, EiaUploadFile[]>

export type EiaCaseStatus = '受理中' | 'AI 分析中' | '报告编制' | '已出具'

export interface EiaCase {
  id: string
  project: string
  org: string
  categories: EiaCategory[]
  status: EiaCaseStatus
  date: string
}

export interface EiaReportFinding {
  item: string
  basis: string
  verdict: string
  ok: boolean
  confidence: string
}

export interface EiaCategoryFindings {
  verdict: string
  rows: EiaReportFinding[]
  summary: string
}

export interface EiaReport {
  category: EiaCategory
  title: string
  no: string
  verdict: string
  findings: EiaReportFinding[]
  summary: string
}
