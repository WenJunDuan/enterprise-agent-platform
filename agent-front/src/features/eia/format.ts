// 纯展示格式化工具，独立于组件文件，避免触发 react-refresh/only-export-components
// （仿 ocr/workbench/shared.ts 把非组件导出单独放置的先例）。

const BYTES_PER_MB = 1024 * 1024

/** 单文件大小的可读展示（MB，一位小数）。 */
export function formatFileSize(size: number): string {
  return `${(size / BYTES_PER_MB).toFixed(1)} MB`
}
