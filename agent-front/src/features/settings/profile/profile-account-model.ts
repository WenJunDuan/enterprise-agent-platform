import type { UpdateProfileCommand } from '@/app/auth/api'
import type { AuthUser } from '@/types/auth'

export type ProfileFormValues = {
  nickname: string
  email: string
  phone: string
  sex: '0' | '1' | '2'
  remark: string
}

export function buildProfileFormValues(user: AuthUser): ProfileFormValues {
  return {
    nickname: user.nickname ?? '',
    email: user.email ?? '',
    phone: user.phone ?? '',
    sex: String(user.sex ?? 0) as '0' | '1' | '2',
    remark: user.remark ?? '',
  }
}

function normalizeOptionalText(value: string) {
  const normalized = value.trim()
  return normalized ? normalized : undefined
}

export function buildProfileUpdatePayload(
  user: AuthUser,
  values: ProfileFormValues
): UpdateProfileCommand {
  if (user.version == null) {
    throw new Error('当前用户版本号缺失')
  }

  return {
    version: user.version,
    nickname: values.nickname.trim(),
    email: normalizeOptionalText(values.email),
    phone: normalizeOptionalText(values.phone),
    sex: Number(values.sex),
    remark: normalizeOptionalText(values.remark),
  }
}
