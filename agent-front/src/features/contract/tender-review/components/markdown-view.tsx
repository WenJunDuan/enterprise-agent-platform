import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * 轻量 Markdown 渲染（R7-#3）。
 *
 * AI 评标流式输出含 `##` 标题、`**粗体**`、`- 列表`、表格等 Markdown 语法，旧实现用
 * whitespace-pre-wrap 纯文本渲染会原样显示符号。此组件用 react-markdown + remark-gfm 渲染，
 * 并以自定义 components 映射各标签样式（贴合卡片内 muted 小字风格），免引 @tailwindcss/typography
 * 插件以降构建风险。无 dangerouslySetInnerHTML，无 XSS 面。
 */

// 标签 → Tailwind 类映射：紧凑、贴合"实时分析输出"卡片的 text-xs muted 风格。
const COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className='mt-3 mb-1 text-sm font-semibold text-foreground'>{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className='mt-3 mb-1 text-sm font-semibold text-foreground'>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className='mt-2 mb-1 text-xs font-semibold text-foreground'>{children}</h3>
  ),
  p: ({ children }) => <p className='my-1 leading-relaxed'>{children}</p>,
  ul: ({ children }) => <ul className='my-1 ml-4 list-disc space-y-0.5'>{children}</ul>,
  ol: ({ children }) => <ol className='my-1 ml-4 list-decimal space-y-0.5'>{children}</ol>,
  li: ({ children }) => <li className='leading-relaxed'>{children}</li>,
  strong: ({ children }) => (
    <strong className='font-semibold text-foreground'>{children}</strong>
  ),
  em: ({ children }) => <em className='italic'>{children}</em>,
  code: ({ children }) => (
    <code className='rounded bg-muted px-1 py-0.5 font-mono text-[0.95em]'>
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className='my-1.5 overflow-x-auto rounded-md bg-muted p-2 font-mono text-[0.95em]'>
      {children}
    </pre>
  ),
  blockquote: ({ children }) => (
    <blockquote className='my-1 border-l-2 border-primary/40 pl-3 italic'>
      {children}
    </blockquote>
  ),
  a: ({ children, href }) => (
    <a href={href} className='text-primary underline' target='_blank' rel='noreferrer'>
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className='my-1.5 overflow-x-auto'>
      <table className='w-full border-collapse text-xs'>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className='border border-border px-2 py-1 text-left font-semibold'>{children}</th>
  ),
  td: ({ children }) => (
    <td className='border border-border px-2 py-1'>{children}</td>
  ),
  hr: () => <hr className='my-2 border-border' />,
}

export function MarkdownView({ children }: { children: string }) {
  return (
    <div className='text-xs leading-relaxed text-foreground'>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
