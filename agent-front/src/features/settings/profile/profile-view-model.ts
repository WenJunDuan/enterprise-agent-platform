export function formatUserSex(sex?: number) {
  switch (sex) {
    case 1:
      return '男'
    case 2:
      return '女'
    default:
      return '未知'
  }
}

export function formatUserStatus(status?: number) {
  switch (status) {
    case 1:
      return '启用'
    case 0:
      return '停用'
    default:
      return '未知'
  }
}

export function formatDateTime(value?: string) {
  if (!value) {
    return '未记录'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function formatText(value?: string | null) {
  const normalized = value?.trim()
  return normalized ? normalized : '未设置'
}
