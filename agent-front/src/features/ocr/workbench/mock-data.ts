import type { FormFillResult, OcrExtractItem } from '../../audit/types'

// 目标表单定义：注入 /ocr/fill 的 form_schema，指导模型把识别底稿映射到这些字段。
// 这里用「项目备案表」作演示；实际接入可换成业务真实表单 schema。
export const FORM_SCHEMA = {
  form_id: 'project_filing',
  fields: [
    { key: '项目名称', component: 'single_line' },
    { key: '项目法人单位', component: 'single_line' },
    { key: '项目代码', component: 'single_line' },
    { key: '项目总投资(万元)', component: 'number' },
    { key: '建设性质', component: 'select', options: ['新建', '改建', '扩建'] },
    { key: '计划开工时间', component: 'date' },
    { key: '总建筑面积(㎡)', component: 'number' },
    { key: '建设地点', component: 'multi_line' },
  ],
  sub_tables: [
    { key: '预测付款', columns: ['付款节点', '触发条件', '比例', '金额(万元)', '计划日期'] },
  ],
}

// 演示用 mock 数据，取自 knowledge/ocr 真实样例（南通算力中心备案证 + 项目库）。
// 「加载示例」用，无需后端 / key 即可预览 UI。

export const MOCK_EXTRACT_ITEMS: OcrExtractItem[] = [
  {
    path: 'knowledge/ocr/南通高新数字科技智能算力中心备案证.pdf',
    kind: 'pdf_text',
    route: 'native',
    blocks: [
      [
        '项目名称： 南通高新数字科技智能算力中心',
        '项目法人单位： 南通高新数字科技发展有限公司',
        '项目代码： 2503-320658-89-04-869947',
        '项目总投资： 7500万元',
        '建设性质： 新建    计划开工时间： 2025',
        '建设地点： 江苏省南通市南通高新技术产业开发区金新街道鹏程大道南侧、世纪大道西侧，江海智汇园C1幢',
        '建设规模及内容： 总建筑面积约12516平方米，包含 AI 算力硬件系统、基础计算硬件系统、存储硬件系统、基础网络硬件系统等。',
      ].join('\n'),
    ],
  },
  {
    path: 'knowledge/ocr/项目库.xlsx',
    kind: 'excel',
    route: 'native',
    tables: [
      {
        name: '附表8 · 高新区2026年度城建工程项目投资计划',
        rows: [
          ['序号', '项目名称', '投资额(万元)', '计划开工'],
          ['1', '南通高新数字科技智能算力中心', '7500', '2025'],
          ['2', '河道护栏维护工程', '320', '2025'],
        ],
      },
    ],
  },
  {
    path: 'knowledge/ocr/河道护栏概算.pdf',
    kind: 'ocr',
    route: 'ocr',
    note: '扫描件（无文本层），需 OCR 引擎识别——本机未部署 PaddleOCR-VL，演示中以占位呈现。',
  },
]

// 付款节点金额自洽：Σ比例 = 100%、Σ金额 = 7500 万（= 项目总投资），
// 对应 runner.py 映射指令里的「Σ金额≈合同总额」自洽校验。
export const MOCK_FORM_FILL: FormFillResult = {
  request_id: 'ocr-demo-0001',
  form_id: 'project_filing',
  fields: [
    { key: '项目名称', component: 'single_line', value: '南通高新数字科技智能算力中心', confidence: 0.98, source: '备案证.pdf' },
    { key: '项目法人单位', component: 'single_line', value: '南通高新数字科技发展有限公司', confidence: 0.96, source: '备案证.pdf' },
    { key: '项目代码', component: 'single_line', value: '2503-320658-89-04-869947', confidence: 0.92, source: '备案证.pdf' },
    { key: '项目总投资(万元)', component: 'number', value: 7500, confidence: 0.95, source: '备案证.pdf / 项目库.xlsx' },
    { key: '建设性质', component: 'select', value: '新建', confidence: 0.99, source: '备案证.pdf' },
    { key: '计划开工时间', component: 'date', value: '2025-01-01', confidence: 0.58, source: '备案证.pdf' },
    { key: '总建筑面积(㎡)', component: 'number', value: 12516, confidence: 0.87, source: '备案证.pdf' },
    {
      key: '建设地点',
      component: 'multi_line',
      value: '江苏省南通市南通高新技术产业开发区金新街道鹏程大道南侧、世纪大道西侧，江海智汇园C1幢',
      confidence: 0.81,
      source: '备案证.pdf',
    },
  ],
  sub_tables: [
    {
      key: '预测付款',
      columns: ['付款节点', '触发条件', '比例', '金额(万元)', '计划日期'],
      rows: [
        { 付款节点: '首付款', 触发条件: '合同签订生效', 比例: '30%', '金额(万元)': 2250, 计划日期: '2025-03' },
        { 付款节点: '进度款', 触发条件: '主体结构封顶', 比例: '40%', '金额(万元)': 3000, 计划日期: '2025-09' },
        { 付款节点: '结算款', 触发条件: '竣工验收合格', 比例: '30%', '金额(万元)': 2250, 计划日期: '2026-06' },
      ],
    },
  ],
  low_confidence: ['计划开工时间', '建设地点'],
  needs_review: true,
  evidence: [
    { source: '备案证.pdf', finding: '项目总投资 7500 万元，与项目库 Excel 投资计划一致' },
    { source: '备案证.pdf', finding: '开工时间仅精确到年(2025)，归一为 2025-01-01，置信度偏低需人工确认' },
    { source: '河道护栏概算.pdf', finding: '扫描件未识别，未参与本次回填' },
  ],
}
