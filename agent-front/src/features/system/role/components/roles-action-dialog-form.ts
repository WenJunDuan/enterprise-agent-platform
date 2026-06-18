import { z } from 'zod'
import { type Role } from '../model'

const roleKeyPattern = /^[A-Za-z][A-Za-z0-9_:-]*$/

function isAllowedValue(value: string, allowedValues: string[]) {
  return allowedValues.includes(value)
}

export const roleActionFormSchema = z.object({
  id: z.string().nullable(),
  roleName: z
    .string()
    .trim()
    .min(1, '请输入角色名称。')
    .max(30, '角色名称长度不能超过 30 个字符。'),
  roleKey: z
    .string()
    .trim()
    .min(1, '请输入角色标识。')
    .max(100, '角色标识长度不能超过 100 个字符。')
    .regex(
      roleKeyPattern,
      '角色标识以英文字母开头，仅支持字母、数字、下划线、冒号和连字符。'
    ),
  orderNum: z
    .string()
    .trim()
    .min(1, '请输入显示顺序。')
    .refine((value) => /^\d+$/.test(value), '显示顺序必须为非负整数。'),
  dataScope: z.string().refine(
    (value) => isAllowedValue(value, ['1', '2', '3', '4', '5']),
    {
      message: '请选择数据权限范围。',
    }
  ),
  status: z.string().refine((value) => isAllowedValue(value, ['0', '1']), {
    message: '请选择角色状态。',
  }),
  remark: z.string().trim().max(500, '备注长度不能超过 500 个字符。'),
  menuIds: z.array(z.string()),
  deptIds: z.array(z.string()),
})

export type RoleActionForm = z.infer<typeof roleActionFormSchema>

export function buildRoleActionDefaultValues(
  currentRow?: Role,
  menuIds: string[] = [],
  deptIds: string[] = []
): RoleActionForm {
  return {
    id: currentRow?.id ?? null,
    roleName: currentRow?.roleName ?? '',
    roleKey: currentRow?.roleKey ?? '',
    orderNum: String(currentRow?.orderNum ?? 0),
    dataScope: String(currentRow?.dataScope ?? 1),
    status: String(currentRow?.status ?? 1),
    remark: currentRow?.remark ?? '',
    menuIds,
    deptIds,
  }
}
