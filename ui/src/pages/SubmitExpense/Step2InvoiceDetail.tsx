import type { SubmitFormData } from '../../types'

const INVOICE_TYPE_OPTIONS = ['增值税专用发票', '增值税普通发票', '电子发票', '定额发票', '境外票据', '无票说明']
const INVOICE_VALIDATION_OPTIONS = ['已验真', '待验真', '验真失败', '境外票据不可验真']
const TRANSPORTATION_OPTIONS = ['飞机', '高铁/火车', '出租车/网约车', '自驾', '混合交通']
const ENTERTAINMENT_PERIOD_OPTIONS = ['早餐', '午餐', '晚餐', '全天会议', '客户活动']

function fieldClass() {
  return 'w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
}

interface Props {
  form: SubmitFormData
  update: <K extends keyof SubmitFormData>(field: K, value: SubmitFormData[K]) => void
}

export default function Step2InvoiceDetail({ form, update }: Props) {
  const isTravel = form.expense_type === '差旅报销'
  const isEntertainment = form.expense_type === '业务招待'

  return (
    <div className="space-y-6">
      {/* Invoice info */}
      <div>
        <h2 className="text-base font-semibold text-gray-800">发票信息</h2>
        <p className="text-xs text-gray-500 mt-1">填写发票验真、抬头与金额一致性</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">发票类型</span>
          <select
            value={form.invoice_type}
            onChange={e => update('invoice_type', e.target.value)}
            className={`${fieldClass()} bg-white`}
          >
            {INVOICE_TYPE_OPTIONS.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">发票号码</span>
          <input
            type="text"
            value={form.invoice_number}
            onChange={e => update('invoice_number', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">开票日期</span>
          <input
            type="date"
            value={form.invoice_issue_date}
            onChange={e => update('invoice_issue_date', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">销售方名称</span>
          <input
            type="text"
            value={form.invoice_seller_name}
            onChange={e => update('invoice_seller_name', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">购买方抬头</span>
          <input
            type="text"
            value={form.invoice_buyer_title}
            onChange={e => update('invoice_buyer_title', e.target.value)}
            className={fieldClass()}
          />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-gray-700 mb-1">发票验真状态</span>
          <select
            value={form.invoice_validation_status}
            onChange={e => update('invoice_validation_status', e.target.value)}
            className={`${fieldClass()} bg-white`}
          >
            {INVOICE_VALIDATION_OPTIONS.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </label>
      </div>

      {/* Travel fields */}
      {isTravel && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-gray-700 border-t border-gray-100 pt-4">差旅行程信息</h3>
          <div className="grid gap-4 md:grid-cols-3">
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">出发城市</span>
              <input
                type="text"
                value={form.travel_from_city}
                onChange={e => update('travel_from_city', e.target.value)}
                className={fieldClass()}
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">到达城市</span>
              <input
                type="text"
                value={form.travel_to_city}
                onChange={e => update('travel_to_city', e.target.value)}
                className={fieldClass()}
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">交通方式</span>
              <select
                value={form.transportation_type}
                onChange={e => update('transportation_type', e.target.value)}
                className={`${fieldClass()} bg-white`}
              >
                {TRANSPORTATION_OPTIONS.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">出差开始日</span>
              <input
                type="date"
                value={form.travel_start_date}
                onChange={e => update('travel_start_date', e.target.value)}
                className={fieldClass()}
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">出差结束日</span>
              <input
                type="date"
                value={form.travel_end_date}
                onChange={e => update('travel_end_date', e.target.value)}
                className={fieldClass()}
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">住宿晚数</span>
              <input
                type="number"
                value={form.hotel_nights}
                onChange={e => update('hotel_nights', e.target.value)}
                className={fieldClass()}
              />
            </label>
          </div>
          <label className="flex items-center gap-2 rounded-lg border border-gray-200 p-3 hover:bg-gray-50">
            <input
              type="checkbox"
              checked={form.has_pre_trip_approval}
              onChange={e => update('has_pre_trip_approval', e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600"
            />
            <span className="text-sm font-medium text-gray-700">已完成事前差旅申请</span>
          </label>
        </div>
      )}

      {/* Entertainment fields */}
      {isEntertainment && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-gray-700 border-t border-gray-100 pt-4">业务招待信息</h3>
          <div className="grid gap-4 md:grid-cols-3">
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">招待对象</span>
              <input
                type="text"
                value={form.entertainment_target}
                onChange={e => update('entertainment_target', e.target.value)}
                className={fieldClass()}
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">客户公司</span>
              <input
                type="text"
                value={form.entertainment_company}
                onChange={e => update('entertainment_company', e.target.value)}
                className={fieldClass()}
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">招待时段</span>
              <select
                value={form.entertainment_period}
                onChange={e => update('entertainment_period', e.target.value)}
                className={`${fieldClass()} bg-white`}
              >
                {ENTERTAINMENT_PERIOD_OPTIONS.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">参与人数</span>
              <input
                type="number"
                value={form.participant_count}
                onChange={e => update('participant_count', e.target.value)}
                className={fieldClass()}
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">人均金额</span>
              <input
                type="number"
                value={form.per_capita_amount}
                onChange={e => update('per_capita_amount', e.target.value)}
                className={fieldClass()}
              />
            </label>
          </div>
          <label className="block">
            <span className="block text-sm font-medium text-gray-700 mb-1">业务目的</span>
            <textarea
              value={form.business_purpose}
              onChange={e => update('business_purpose', e.target.value)}
              rows={3}
              className={`${fieldClass()} resize-y`}
            />
          </label>
        </div>
      )}
    </div>
  )
}
