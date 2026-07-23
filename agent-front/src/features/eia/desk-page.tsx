import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'

// T1 路由壳占位：受理工作台实现见 T4（desk-page.tsx 将替换本文件内容）。
export function EiaDeskPage() {
  return (
    <>
      <Header fixed />
      <Main className='space-y-5'>
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>
            受理工作台
          </h1>
          <p className='text-sm text-muted-foreground'>
            查看检测报告受理案件与分类报告进度。
          </p>
        </div>
      </Main>
    </>
  )
}
