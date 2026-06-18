import { z } from 'zod'

function isAllowedStatus(value: string) {
  return value === '0' || value === '1'
}

function isAllowedDefaultFlag(value: string) {
  return value === 'Y' || value === 'N'
}

const dictTypePattern = /^[A-Za-z][A-Za-z0-9:_-]*$/

export const dictTypeFormSchema = z.object({
  id: z.string().nullable(),
  dictName: z
    .string()
    .trim()
    .min(1, '请输入分组名称。')
    .max(50, '分组名称长度不能超过 50 个字符。'),
  dictType: z
    .string()
    .trim()
    .min(1, '请输入分组编码。')
    .max(100, '分组编码长度不能超过 100 个字符。')
    .regex(
      dictTypePattern,
      '分组编码需以字母开头，仅支持字母、数字、下划线、冒号和连字符。'
    ),
  status: z.string().refine(isAllowedStatus, {
    message: '请选择分组状态。',
  }),
  remark: z.string().trim().max(500, '备注长度不能超过 500 个字符。'),
})

export const dictDataFormSchema = z.object({
  id: z.string().nullable(),
  dictType: z.string().trim().min(1, '缺少字典分组，请重新选择。'),
  dictLabel: z
    .string()
    .trim()
    .min(1, '请输入字典名称。')
    .max(100, '字典名称长度不能超过 100 个字符。'),
  dictValue: z
    .string()
    .trim()
    .min(1, '请输入字典编码。')
    .max(100, '字典编码长度不能超过 100 个字符。'),
  dictSort: z
    .string()
    .trim()
    .min(1, '请输入排序值。')
    .refine((value) => /^\d+$/.test(value), {
      message: '排序值必须为非负整数。',
    }),
  cssClass: z.string().trim().max(100, '标签样式长度不能超过 100 个字符。'),
  listClass: z
    .string()
    .trim()
    .max(100, '列表样式长度不能超过 100 个字符。'),
  isDefault: z.string().refine(isAllowedDefaultFlag, {
    message: '请选择是否默认。',
  }),
  status: z.string().refine(isAllowedStatus, {
    message: '请选择字典状态。',
  }),
  remark: z.string().trim().max(500, '备注长度不能超过 500 个字符。'),
})

export type DictTypeFormValues = z.input<typeof dictTypeFormSchema>
export type DictTypeForm = z.output<typeof dictTypeFormSchema>

export type DictDataFormValues = z.input<typeof dictDataFormSchema>
export type DictDataForm = z.output<typeof dictDataFormSchema>

type DictTypeField = keyof DictTypeFormValues
type DictDataField = keyof DictDataFormValues

const dictTypeFieldPatterns: Array<{ field: DictTypeField; pattern: RegExp }> = [
  { field: 'dictName', pattern: /分组名称|字典名称/ },
  { field: 'dictType', pattern: /分组编码|字典类型|dictType/i },
  { field: 'status', pattern: /状态/ },
  { field: 'remark', pattern: /备注/ },
]

const dictDataFieldPatterns: Array<{ field: DictDataField; pattern: RegExp }> = [
  { field: 'dictLabel', pattern: /字典名称|标签/ },
  { field: 'dictValue', pattern: /字典编码|字典值|编码/ },
  { field: 'dictSort', pattern: /排序|dictSort/i },
  { field: 'cssClass', pattern: /标签样式|css/i },
  { field: 'listClass', pattern: /列表样式|listClass/i },
  { field: 'isDefault', pattern: /默认/ },
  { field: 'status', pattern: /状态/ },
  { field: 'remark', pattern: /备注/ },
  { field: 'dictType', pattern: /字典类型|分组/ },
]

function extractServerErrors<TField extends string>(
  message: string | undefined,
  fields: Set<TField>,
  fallbackPatterns: Array<{ field: TField; pattern: RegExp }>
) {
  const fieldErrors: Partial<Record<TField, string>> = {}
  const generalErrors: string[] = []

  if (!message?.trim()) {
    return { fieldErrors, generalErrors }
  }

  for (const rawSegment of message.split(';')) {
    const segment = rawSegment.trim()
    if (!segment) {
      continue
    }

    const explicit = segment.match(/^([A-Za-z][\w.]*)\s*:\s*(.+)$/)
    const fieldName = explicit?.[1]?.split('.').pop() as TField | undefined
    const fieldMessage = explicit?.[2]?.trim()

    if (fieldName && fieldMessage && fields.has(fieldName)) {
      fieldErrors[fieldName] ??= fieldMessage
      continue
    }

    const fallbackField = fallbackPatterns.find(({ pattern }) =>
      pattern.test(segment)
    )?.field

    if (fallbackField) {
      fieldErrors[fallbackField] ??= segment
      continue
    }

    generalErrors.push(segment)
  }

  return { fieldErrors, generalErrors }
}

export function extractDictTypeServerErrors(message?: string) {
  return extractServerErrors(
    message,
    new Set<DictTypeField>(['id', 'dictName', 'dictType', 'status', 'remark']),
    dictTypeFieldPatterns
  )
}

export function extractDictDataServerErrors(message?: string) {
  return extractServerErrors(
    message,
    new Set<DictDataField>([
      'id',
      'dictType',
      'dictLabel',
      'dictValue',
      'dictSort',
      'cssClass',
      'listClass',
      'isDefault',
      'status',
      'remark',
    ]),
    dictDataFieldPatterns
  )
}
