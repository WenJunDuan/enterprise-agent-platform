import { z } from 'zod'

const phonePattern = /^1[3-9]\d{9}$/
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function isAllowedStatus(value: string) {
  return value === '0' || value === '1'
}

export const deptFormSchema = z.object({
  parentId: z.string().trim().min(1, '请选择父部门。'),
  deptName: z
    .string()
    .trim()
    .min(1, '请输入部门名称。')
    .max(50, '部门名称长度不能超过 50 个字符。'),
  orderNum: z
    .string()
    .trim()
    .min(1, '请输入显示顺序。')
    .refine((value) => value === '' || /^\d+$/.test(value), {
      message: '显示顺序必须为非负整数。',
    }),
  leader: z
    .string()
    .trim()
    .min(1, '请输入部门负责人。')
    .max(20, '部门负责人长度不能超过 20 个字符。'),
  phone: z
    .string()
    .trim()
    .min(1, '请输入联系电话。')
    .refine((value) => value === '' || phonePattern.test(value), {
      message: '联系电话格式不正确。',
    }),
  email: z
    .string()
    .trim()
    .refine((value) => value === '' || emailPattern.test(value), '邮箱格式不正确。'),
  status: z.string().refine(isAllowedStatus, {
    message: '请选择部门状态。',
  }),
})

export type DeptFormValues = z.input<typeof deptFormSchema>
export type DeptForm = z.output<typeof deptFormSchema>

type DeptFormField = keyof DeptFormValues

const deptFormFields = new Set<DeptFormField>([
  'parentId',
  'deptName',
  'orderNum',
  'leader',
  'phone',
  'email',
  'status',
])

const fieldKeywordMappings: Array<{
  field: DeptFormField
  pattern: RegExp
}> = [
  { field: 'parentId', pattern: /父部门|上级部门|子部门为父部门/ },
  { field: 'deptName', pattern: /部门名称/ },
  { field: 'orderNum', pattern: /显示顺序/ },
  { field: 'leader', pattern: /部门负责人|负责人/ },
  { field: 'phone', pattern: /联系电话|手机号|手机/ },
  { field: 'email', pattern: /邮箱/ },
  { field: 'status', pattern: /状态/ },
]

export function extractDeptServerErrors(message?: string) {
  const fieldErrors: Partial<Record<DeptFormField, string>> = {}
  const generalErrors: string[] = []

  if (!message?.trim()) {
    return { fieldErrors, generalErrors }
  }

  for (const rawSegment of message.split(';')) {
    const segment = rawSegment.trim()

    if (!segment) {
      continue
    }

    const matchedFieldMessage = segment.match(/^([A-Za-z][\w.]*)\s*:\s*(.+)$/)
    const normalizedField = matchedFieldMessage?.[1]?.split('.').pop()
    const explicitMessage = matchedFieldMessage?.[2]?.trim()

    if (
      normalizedField &&
      explicitMessage &&
      deptFormFields.has(normalizedField as DeptFormField)
    ) {
      fieldErrors[normalizedField as DeptFormField] ??= explicitMessage
      continue
    }

    const fallbackField = fieldKeywordMappings.find(({ pattern }) =>
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
