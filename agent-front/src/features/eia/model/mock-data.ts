import type {
  EiaCase,
  EiaCategory,
  EiaCategoryDef,
  EiaCategoryFindings,
  EiaFilesByCategory,
} from '../types'
import type { StreamScriptLine } from './stream-script'

// mock-first 数据层(design.md A4)：本 sprint 不建后端，分类流式脚本、判定依据、案件列表均
// 取自 design/index.html 静态稿的演示内容，仅供「加载示例」按钮 / 受理工作台预览注入——首屏
// 提交向导四类材料仍为空(critic R1-F3)，不在此处预置到 wizard 初始 state。

export const EIA_CATEGORIES: EiaCategoryDef[] = [
  {
    key: 'water',
    glyph: '水',
    title: '水质检测材料',
    hint: '地表水/地下水/废水监测数据、采样记录、水质点位图。',
  },
  {
    key: 'soil',
    glyph: '土',
    title: '土壤检测材料',
    hint: '土壤采样检测报告、点位布设图、背景值资料。',
  },
  {
    key: 'air',
    glyph: '气',
    title: '大气 / 废气材料',
    hint: '有组织/无组织废气监测数据、排放口参数、环境空气质量数据。',
  },
  {
    key: 'noise',
    glyph: '声',
    title: '噪声检测材料',
    hint: '厂界噪声、敏感点噪声监测记录及点位示意图。',
  },
]

export const EIA_CATEGORY_GLYPH: Record<EiaCategory, string> = {
  water: '水',
  soil: '土',
  air: '气',
  noise: '声',
}

/** 「加载示例」按钮注入的演示文件（无真实 File 对象，走 mock 分析路径）。 */
export const MOCK_EIA_SAMPLE_FILES: EiaFilesByCategory = {
  water: [
    { id: 'sample-water-1', name: '地表水监测数据报表_2026Q2.pdf', size: 4404019 },
    { id: 'sample-water-2', name: '废水排放口采样记录_0715.pdf', size: 1887436 },
  ],
  soil: [{ id: 'sample-soil-1', name: '土壤采样检测报告_北区3点位.pdf', size: 6815744 }],
  air: [
    { id: 'sample-air-1', name: '有组织废气监测数据_RTO排口.pdf', size: 3250585 },
    { id: 'sample-air-2', name: '无组织废气布点示意图.png', size: 2516582 },
  ],
  noise: [{ id: 'sample-noise-1', name: '厂界噪声昼夜间监测记录.pdf', size: 1258291 }],
}

export const EIA_CATEGORY_STREAM_LINES: Record<EiaCategory, StreamScriptLine[]> =
  {
    water: [
      {
        text: '▸ [水] 解析《地表水监测数据报表_2026Q2.pdf》— 提取 24 组监测数据',
        tone: 'cat',
      },
      {
        text: 'pH 7.2–7.8 · COD 14.6 mg/L · 氨氮 0.31 mg/L · 总磷 0.08 mg/L',
        tone: 'data',
      },
      { text: '比对 GB 3838-2002 地表水 III 类限值 → 全部因子低于限值', tone: 'data' },
      { text: '✓ 水类分析完成 · 结论:达标 · 置信度 95%', tone: 'ok' },
    ],
    soil: [
      {
        text: '▸ [土] 解析《土壤采样检测报告_北区3点位.pdf》— 提取 8 项重金属指标',
        tone: 'cat',
      },
      {
        text: '镉 0.14 mg/kg · 铅 21.3 mg/kg · 砷 6.8 mg/kg · 汞 0.05 mg/kg',
        tone: 'data',
      },
      { text: '比对 GB 36600-2018 第二类用地筛选值 → 全部低于筛选值', tone: 'data' },
      { text: '✓ 土类分析完成 · 结论:达标 · 置信度 93%', tone: 'ok' },
    ],
    air: [
      {
        text: '▸ [气] 解析《有组织废气监测数据_RTO排口.pdf》— 提取 3 个排口 12 项因子',
        tone: 'cat',
      },
      {
        text: '颗粒物 8.2 mg/m³ · SO₂ 11 mg/m³ · NOx 42 mg/m³ · 非甲烷总烃 48 mg/m³',
        tone: 'data',
      },
      {
        text: '比对 GB 16297-1996 二级标准 → 非甲烷总烃达限值 80%,标记为关注项',
        tone: 'warn',
      },
      {
        text: '核验无组织布点:下风向 3 点 + 参照点 1 点,符合 HJ/T 55 要求',
        tone: 'data',
      },
      { text: '✓ 气类分析完成 · 结论:关注 · 建议补充活性炭吸附装置运行台账', tone: 'warn' },
    ],
    noise: [
      {
        text: '▸ [声] 解析《厂界噪声昼夜间监测记录.pdf》— 提取 4 个测点昼夜数据',
        tone: 'cat',
      },
      { text: '昼间 54.2–57.8 dB(A) · 夜间 44.1–47.6 dB(A)', tone: 'data' },
      { text: '比对 GB 12348-2008 2 类区限值(昼 60 / 夜 50)→ 全部达标', tone: 'data' },
      { text: '✓ 声类分析完成 · 结论:达标 · 置信度 96%', tone: 'ok' },
    ],
  }

export const EIA_CATEGORY_FINDINGS: Record<EiaCategory, EiaCategoryFindings> = {
  water: {
    verdict: '达标',
    rows: [
      { item: 'pH / COD / 氨氮 / 总磷', basis: 'GB 3838-2002 III 类', verdict: '通过', ok: true, confidence: '95%' },
      { item: '采样断面与频次 (HJ 91.1)', basis: '24 组 / 3 断面', verdict: '通过', ok: true, confidence: '97%' },
      { item: '废水排放口规范化', basis: '2 个排口', verdict: '通过', ok: true, confidence: '94%' },
    ],
    summary:
      '各断面监测因子均低于《地表水环境质量标准》III 类限值,断面与频次符合技术规范,预判达标。',
  },
  soil: {
    verdict: '达标',
    rows: [
      { item: '重金属八项筛选值比对', basis: 'GB 36600-2018 二类', verdict: '通过', ok: true, confidence: '93%' },
      { item: '点位布设 (HJ/T 166)', basis: '3 点位 + 对照点', verdict: '通过', ok: true, confidence: '92%' },
      { item: '与区域背景值一致性', basis: '偏差 < 15%', verdict: '通过', ok: true, confidence: '90%' },
    ],
    summary: '各点位重金属含量低于建设用地第二类筛选值,与区域背景值一致,预判达标。',
  },
  air: {
    verdict: '关注',
    rows: [
      { item: '非甲烷总烃小时浓度', basis: '48 / 60 mg/m³', verdict: '关注', ok: false, confidence: '88%' },
      { item: '颗粒物 / SO₂ / NOx', basis: 'GB 16297-1996 二级', verdict: '通过', ok: true, confidence: '96%' },
      { item: '无组织布点 (HJ/T 55)', basis: '3+1 点', verdict: '通过', ok: true, confidence: '93%' },
    ],
    summary:
      '非甲烷总烃小时浓度达限值 80%,建议要求补充活性炭吸附装置运行台账后出具正式意见;其余因子达标。',
  },
  noise: {
    verdict: '达标',
    rows: [
      { item: '厂界昼间 / 夜间等效声级', basis: '57.8 / 47.6 dB(A)', verdict: '通过', ok: true, confidence: '96%' },
      { item: '敏感点影响预判', basis: '2 类区限值', verdict: '通过', ok: true, confidence: '92%' },
      { item: '测点布设合规性', basis: 'GB 12348-2008', verdict: '通过', ok: true, confidence: '97%' },
    ],
    summary: '厂界及敏感点昼夜间等效声级均满足 2 类声环境功能区要求,预判达标。',
  },
}

/** 受理工作台案件列表演示数据。 */
export const MOCK_EIA_CASES: EiaCase[] = [
  { id: 'HP-2026-0718', project: '临港新片区智造产业园二期', org: '临港产投集团', categories: ['water', 'air', 'noise'], status: '已出具', date: '07-22 16:20' },
  { id: 'HP-2026-0717', project: '城东污水处理厂扩建工程', org: '市水务集团', categories: ['water', 'soil'], status: '报告编制', date: '07-22 11:05' },
  { id: 'HP-2026-0716', project: '生物医药产业基地一期', org: '康桥生物', categories: ['water', 'air'], status: '已出具', date: '07-21 17:32' },
  { id: 'HP-2026-0715', project: '高新区半导体封测基地', org: '芯合微电子', categories: ['air'], status: 'AI 分析中', date: '07-21 15:48' },
  { id: 'HP-2026-0714', project: '滨江商务区综合体项目', org: '滨江置业', categories: ['noise', 'air'], status: '已出具', date: '07-21 09:30' },
  { id: 'HP-2026-0712', project: '北郊固废资源化利用中心', org: '环兴固废', categories: ['soil', 'water'], status: '受理中', date: '07-20 14:12' },
  { id: 'HP-2026-0711', project: '智能装备制造车间技改', org: '精工机械', categories: ['air', 'noise'], status: '报告编制', date: '07-19 16:40' },
  { id: 'HP-2026-0709', project: '轨道交通 7 号线延伸段', org: '城铁建设', categories: ['noise'], status: '已出具', date: '07-18 10:02' },
  { id: 'HP-2026-0708', project: '临江化工园区雨污分流改造', org: '园区管委会', categories: ['water', 'soil', 'air'], status: '已出具', date: '07-17 14:55' },
]
