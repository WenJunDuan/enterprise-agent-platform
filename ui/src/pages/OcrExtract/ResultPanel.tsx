import type { FormComponent, FormFillField, FormFillResult, FormFillSubTable } from '../../types'
import { CONFIDENCE_STYLE, confidenceLevel, formatFieldValue, type RecognizePhase } from './shared'

const COMPONENT_LABELS: Record<FormComponent, string> = {
  single_line: '单行',
  multi_line: '多行',
  select: '下拉',
  number: '数字',
  date: '日期',
  sub_table: '子表',
}

interface Props {
  formFill: FormFillResult | null
  phase: RecognizePhase
}

/** 置信度徽标：百分比 + 高/中/低文字，颜色之外保留文字（a11y）。 */
function ConfidenceBadge({ confidence }: { confidence: number }) {
  const style = CONFIDENCE_STYLE[confidenceLevel(confidence)]
  return (
    <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${style.bg} ${style.text}`}>
      {Math.round(confidence * 100)}% · {style.label}
    </span>
  )
}

/** 单个回填字段行；低置信字段加红色左边框高亮。 */
function FieldRow({ field, flagged }: { field: FormFillField; flagged: boolean }) {
  return (
    <div className={`rounded-lg border p-3 ${flagged ? 'border-l-2 border-red-300 bg-red-50/40' : 'border-gray-200'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-xs text-gray-500">{field.key}</p>
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
              {COMPONENT_LABELS[field.component]}
            </span>
          </div>
          <p className="mt-0.5 break-words text-sm font-medium text-gray-800">{formatFieldValue(field.value)}</p>
          {field.source && <p className="mt-0.5 text-[11px] text-gray-400">来源：{field.source}</p>}
        </div>
        <ConfidenceBadge confidence={field.confidence} />
      </div>
    </div>
  )
}

/** 付款节点等子表渲染；列顺序优先用契约的 columns，缺省时取首行键。 */
function SubTable({ table }: { table: FormFillSubTable }) {
  const columns = table.columns ?? Object.keys(table.rows[0] ?? {})
  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium text-gray-700">{table.key}</p>
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-gray-50 text-gray-600">
              {columns.map(col => (
                <th key={col} className="border-b border-gray-200 px-3 py-2 text-left font-medium">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, ri) => (
              <tr key={ri} className="text-gray-700">
                {columns.map(col => (
                  <td key={col} className="border-b border-gray-100 px-3 py-2">
                    {formatFieldValue(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 p-10 text-center">
      <p className="text-sm text-gray-500">尚无回填结果</p>
      <p className="mt-1 text-xs text-gray-400">左侧上传文档并点击「开始识别」，结果会展示在这里</p>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="space-y-3">
      <div className="h-12 animate-pulse rounded-lg bg-gray-100" />
      <div className="h-16 animate-pulse rounded-lg bg-gray-100" />
      <div className="h-16 animate-pulse rounded-lg bg-gray-100" />
      <div className="h-24 animate-pulse rounded-lg bg-gray-100" />
    </div>
  )
}

/** 回填结果主体：需复核提示 + 字段列表 + 付款子表 + 证据。 */
function ResultBody({ formFill }: { formFill: FormFillResult }) {
  const flagged = new Set(formFill.low_confidence ?? [])
  return (
    <div className="space-y-5">
      {formFill.needs_review && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <svg
            className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M10.29 3.86l-8.48 14.7A1 1 0 002.7 20h18.6a1 1 0 00.88-1.44l-8.48-14.7a1 1 0 00-1.72 0z" />
          </svg>
          <div>
            <p className="text-sm font-medium text-amber-800">需人工复核</p>
            {flagged.size > 0 && (
              <p className="mt-0.5 text-xs text-amber-700">
                {flagged.size} 个字段置信度偏低：{[...flagged].join('、')}
              </p>
            )}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-700">字段（{formFill.fields.length}）</p>
        {formFill.fields.map(field => (
          <FieldRow key={field.key} field={field} flagged={flagged.has(field.key)} />
        ))}
      </div>

      {formFill.sub_tables.map(table => (
        <SubTable key={table.key} table={table} />
      ))}

      {formFill.evidence && formFill.evidence.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-sm font-medium text-gray-700">证据</p>
          <ul className="space-y-1">
            {formFill.evidence.map((item, i) => (
              <li key={i} className="text-xs text-gray-600">
                <span className="font-medium text-gray-500">{item.source}：</span>
                {item.finding}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** OCR 页面右栏：识别 → 表单回填结果（字段 + 付款子表 + 复核标记）。 */
export default function ResultPanel({ formFill, phase }: Props) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="mb-4">
        <h2 className="text-base font-semibold text-gray-800">回填结果</h2>
        <p className="mt-1 text-xs text-gray-500">字段映射 + 付款节点抽取，带置信度与需复核标记</p>
      </div>
      {phase === 'recognizing' ? <LoadingState /> : formFill ? <ResultBody formFill={formFill} /> : <EmptyState />}
    </section>
  )
}
