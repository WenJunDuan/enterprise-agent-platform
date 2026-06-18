/**
 * 后端 Long 类型（雪花 ID、外键）在前端统一以 string 形式携带。
 *
 * 原因：JS Number 的安全整数上限是 2^53-1（16 位十进制），而雪花 ID 约 19 位，
 * 经过 `Number("1889234567890123456")` 后变成 `1889234567890123500`，
 * 再 JSON 序列化回后端时 id 不匹配，导致唯一性校验、关联查询、乐观锁等全部失败。
 *
 * 凡是后端字段类型是 Long 且承载业务含义（主键/外键）时，前端必须：
 * - 响应侧：`normalizeXxx` 用 `toId`/`toIdList` 把值强制为 string
 * - 请求侧：payload 里对应字段也用 `toId`/`toIdList`，禁止走 `Number()`
 *
 * 后端 `com.alpha.framework.config.JacksonConfig` 已把 Long/BigInteger
 * 序列化为 string，配合本工具即可保证双向精度。
 */
export type Id = string

export function toId(value: unknown): Id {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'bigint') return value.toString()
  return ''
}

export function toIdList(values: unknown): Id[] {
  if (!Array.isArray(values)) return []
  return values.map(toId).filter((value) => value.length > 0)
}

export function isSameId(a: Id | null | undefined, b: Id | null | undefined) {
  const left = (a ?? '').trim()
  const right = (b ?? '').trim()
  return left.length > 0 && left === right
}
