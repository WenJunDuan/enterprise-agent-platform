import { z } from 'zod'
import { type User, type UserEditDetail } from '../data/schema'

const usernamePattern = /^[a-zA-Z0-9_]+$/
const phonePattern = /^1[3-9]\d{9}$/
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function isAllowedValue(value: string, allowedValues: string[]) {
  return allowedValues.includes(value)
}

export const userActionFormSchema = z
  .object({
    id: z.string().nullable(),
    version: z.string().nullable(),
    username: z
      .string()
      .trim()
      .min(1, '请输入用户名。')
      .min(2, '用户名长度必须在 2-20 之间。')
      .max(20, '用户名长度必须在 2-20 之间。')
      .regex(usernamePattern, '用户名只能包含字母、数字、下划线。'),
    nickname: z
      .string()
      .trim()
      .min(1, '请输入昵称。')
      .max(10, '昵称长度不能超过 10 个字符。'),
    phone: z
      .string()
      .trim()
      .min(1, '请输入手机号。')
      .regex(phonePattern, '手机号格式不正确。'),
    email: z
      .string()
      .trim()
      .min(1, '请输入邮箱地址。')
      .regex(emailPattern, '邮箱格式不正确。'),
    sex: z.string().refine((value) => isAllowedValue(value, ['0', '1', '2']), {
      message: '请选择性别。',
    }),
    deptId: z.string().trim().min(1, '请选择所属部门。'),
    status: z.string().refine((value) => isAllowedValue(value, ['0', '1']), {
      message: '请选择账号状态。',
    }),
    roleIds: z.array(z.string().trim().min(1)).min(1, '请至少选择一个角色。'),
    remark: z.string().trim().max(500, '备注长度不能超过 500 个字符。'),
    password: z.string(),
    confirmPassword: z.string(),
    isEdit: z.boolean(),
  })
  .refine(
    (data) => {
      if (data.isEdit) return true
      return data.password.trim().length > 0
    },
    {
      message: '请输入密码。',
      path: ['password'],
    }
  )
  .refine(
    (data) => {
      if (data.isEdit) return true
      return data.password.trim().length >= 8
    },
    {
      message: '密码长度至少为 8 位。',
      path: ['password'],
    }
  )
  .refine(
    (data) => {
      if (data.isEdit) return true
      return /[a-z]/.test(data.password)
    },
    {
      message: '密码至少包含一个小写字母。',
      path: ['password'],
    }
  )
  .refine(
    (data) => {
      if (data.isEdit) return true
      return /\d/.test(data.password)
    },
    {
      message: '密码至少包含一个数字。',
      path: ['password'],
    }
  )
  .refine(
    (data) => {
      if (data.isEdit) return true
      return data.password === data.confirmPassword
    },
    {
      message: '两次输入的密码不一致。',
      path: ['confirmPassword'],
    }
  )

export type UserActionForm = z.infer<typeof userActionFormSchema>

export function buildUserActionDefaultValues(
  currentRow?: User,
  detail?: UserEditDetail,
  roleIds: string[] = []
): UserActionForm {
  const isEdit = Boolean(currentRow)
  const source = detail ?? currentRow

  return {
    id: detail?.id ?? currentRow?.id ?? null,
    version: detail?.version ?? null,
    username: source?.username ?? '',
    nickname: source?.nickname ?? '',
    phone: source?.phone ?? '',
    email: source?.email ?? '',
    sex:
      source?.sex === null || source?.sex === undefined
        ? ''
        : String(source.sex),
    deptId:
      detail?.deptId === null || detail?.deptId === undefined
        ? ''
        : String(detail.deptId),
    status:
      source?.status === null || source?.status === undefined
        ? '1'
        : String(source.status),
    roleIds,
    remark: source?.remark ?? '',
    password: '',
    confirmPassword: '',
    isEdit,
  }
}
