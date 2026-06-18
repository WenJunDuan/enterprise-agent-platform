import { z } from 'zod'

const permsPattern = /^[A-Za-z][A-Za-z0-9:_-]*$/

function isAllowedFlag(value: string) {
  return value === '0' || value === '1'
}

export const menuFormSchema = z
  .object({
    parentId: z.string().trim().min(1, '请选择上级菜单。'),
    menuType: z.enum(['M', 'C', 'F'], {
      message: '请选择菜单类型。',
    }),
    menuName: z
      .string()
      .trim()
      .min(1, '请输入菜单名称。')
      .max(50, '菜单名称长度不能超过 50 个字符。'),
    orderNum: z
      .string()
      .trim()
      .min(1, '请输入显示顺序。')
      .refine((value) => /^\d+$/.test(value), {
        message: '显示顺序必须为非负整数。',
      }),
    path: z
      .string()
      .trim()
      .max(200, '路由地址长度不能超过 200 个字符。'),
    component: z
      .string()
      .trim()
      .max(200, '组件路径长度不能超过 200 个字符。'),
    queryParam: z
      .string()
      .trim()
      .max(200, '路由参数长度不能超过 200 个字符。'),
    isFrame: z.string().refine(isAllowedFlag, {
      message: '请选择是否外链。',
    }),
    isCache: z.string().refine(isAllowedFlag, {
      message: '请选择是否缓存。',
    }),
    visible: z.string().refine(isAllowedFlag, {
      message: '请选择显示状态。',
    }),
    perms: z
      .string()
      .trim()
      .max(100, '权限标识长度不能超过 100 个字符。'),
    icon: z
      .string()
      .trim()
      .max(100, '图标标识长度不能超过 100 个字符。'),
    status: z.string().refine(isAllowedFlag, {
      message: '请选择菜单状态。',
    }),
    remark: z
      .string()
      .trim()
      .max(500, '备注长度不能超过 500 个字符。'),
  })
  .superRefine((value, ctx) => {
    if ((value.menuType === 'M' || value.menuType === 'C') && !value.path) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['path'],
        message: '目录/菜单路由地址不能为空。',
      })
    }

    if (value.menuType === 'C' && !value.component) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['component'],
        message: '菜单组件路径不能为空。',
      })
    }

    if (value.menuType === 'F' && !value.perms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['perms'],
        message: '按钮权限标识不能为空。',
      })
    }

    if (value.perms && !permsPattern.test(value.perms)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['perms'],
        message: '权限标识格式不正确。',
      })
    }
  })

export type MenuFormValues = z.input<typeof menuFormSchema>
export type MenuForm = z.output<typeof menuFormSchema>

type MenuFormField = keyof MenuFormValues

const menuFormFields = new Set<MenuFormField>([
  'parentId',
  'menuType',
  'menuName',
  'orderNum',
  'path',
  'component',
  'queryParam',
  'isFrame',
  'isCache',
  'visible',
  'perms',
  'icon',
  'status',
  'remark',
])

const fieldKeywordMappings: Array<{
  field: MenuFormField
  pattern: RegExp
}> = [
  { field: 'parentId', pattern: /父菜单|上级菜单/ },
  { field: 'menuType', pattern: /菜单类型/ },
  { field: 'menuName', pattern: /菜单名称|名称/ },
  { field: 'orderNum', pattern: /显示顺序|排序/ },
  { field: 'path', pattern: /路由地址|访问路径|path/i },
  { field: 'component', pattern: /组件路径|component/i },
  { field: 'queryParam', pattern: /路由参数|query/i },
  { field: 'isFrame', pattern: /外链/ },
  { field: 'isCache', pattern: /缓存/ },
  { field: 'visible', pattern: /显示状态|可见/ },
  { field: 'perms', pattern: /权限|perms/i },
  { field: 'icon', pattern: /图标|icon/i },
  { field: 'status', pattern: /状态/ },
  { field: 'remark', pattern: /备注/ },
]

export function extractMenuServerErrors(message?: string) {
  const fieldErrors: Partial<Record<MenuFormField, string>> = {}
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
      menuFormFields.has(normalizedField as MenuFormField)
    ) {
      fieldErrors[normalizedField as MenuFormField] ??= explicitMessage
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
