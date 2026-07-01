/** 分数格式化：整数直出，小数保留一位（评标分常为 0.5 步长）。 */
export function formatScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}
