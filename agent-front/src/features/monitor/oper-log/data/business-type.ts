export type BusinessTypeMeta = {
  label: string
  variant: 'default' | 'secondary' | 'destructive' | 'outline'
}

export const BUSINESS_TYPE_MAP: Record<number, BusinessTypeMeta> = {
  0: { label: '其它', variant: 'outline' },
  1: { label: '新增', variant: 'default' },
  2: { label: '修改', variant: 'secondary' },
  3: { label: '删除', variant: 'destructive' },
  4: { label: '查询', variant: 'outline' },
  5: { label: '授权', variant: 'secondary' },
  6: { label: '导出', variant: 'secondary' },
  7: { label: '导入', variant: 'secondary' },
  8: { label: '强退', variant: 'destructive' },
  9: { label: '清空', variant: 'destructive' },
}

export function getBusinessTypeMeta(code: number): BusinessTypeMeta {
  return BUSINESS_TYPE_MAP[code] ?? { label: '未知', variant: 'outline' }
}

export const BUSINESS_TYPE_OPTIONS = Object.entries(BUSINESS_TYPE_MAP).map(
  ([value, meta]) => ({ value: Number(value), label: meta.label })
)
