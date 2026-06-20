import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { TenderReviewScreen } from '../types'

const headingCopy: Record<TenderReviewScreen, { title: string; desc: string }> =
  {
    dashboard: {
      title: '项目管理',
      desc: '查看招投标项目、审核进度与复核状态。',
    },
    create: {
      title: '创建评审',
      desc: '填写项目信息并上传招标文件与投标文件。',
    },
    history: {
      title: '历史评审',
      desc: '已完成的评审项目，可查看分析中心与完整审核报告。',
    },
    analysis: {
      title: '分析中心',
      desc: '查看评审要点、评分对比和投标文件原文。',
    },
    report: {
      title: '审核报告',
      desc: '预览并导出评标报告。',
    },
  }

type PageHeadingProps = {
  activeScreen: TenderReviewScreen
  onBack: () => void
}

export function PageHeading({
  activeScreen,
  onBack,
}: PageHeadingProps) {
  const copy = headingCopy[activeScreen]

  return (
    <div className='flex flex-col gap-3 md:flex-row md:items-start md:justify-between'>
      <div>
        <h1 className='text-2xl font-semibold tracking-tight'>{copy.title}</h1>
        <p className='text-sm text-muted-foreground'>{copy.desc}</p>
      </div>
      {activeScreen === 'create' ? (
        <Button variant='outline' onClick={onBack}>
          <ArrowLeft className='size-4' />
          返回
        </Button>
      ) : null}
    </div>
  )
}
