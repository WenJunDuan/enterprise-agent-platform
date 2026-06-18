import type { ProfileFormValues } from './profile-account-model'

type ProfileFormField = keyof ProfileFormValues

const profileFormFields = new Set<ProfileFormField>([
  'nickname',
  'email',
  'phone',
  'sex',
  'remark',
])

const fieldKeywordMappings: Array<{
  field: ProfileFormField
  pattern: RegExp
}> = [
  { field: 'nickname', pattern: /昵称/ },
  { field: 'email', pattern: /邮箱/ },
  { field: 'phone', pattern: /手机/ },
  { field: 'sex', pattern: /性别/ },
  { field: 'remark', pattern: /备注/ },
]

export function extractProfileServerErrors(message?: string) {
  const fieldErrors: Partial<Record<ProfileFormField, string>> = {}
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
      profileFormFields.has(normalizedField as ProfileFormField)
    ) {
      fieldErrors[normalizedField as ProfileFormField] ??= explicitMessage
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
