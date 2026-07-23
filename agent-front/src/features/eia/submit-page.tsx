import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'

// T1 路由壳占位：三步提交向导实现见 T3（submit-page.tsx 将替换本文件内容）。
export function EiaSubmitPage() {
  return (
    <>
      <Header fixed />
      <Main className='space-y-5'>
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>
            提交检测报告
          </h1>
          <p className='text-sm text-muted-foreground'>
            按水、土、气、声分类上传检测材料，AI 分析后出具分类报告。
          </p>
        </div>
      </Main>
    </>
  )
}
