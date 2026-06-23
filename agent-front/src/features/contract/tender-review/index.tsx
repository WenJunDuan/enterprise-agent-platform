import { useSearch } from '@tanstack/react-router'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { PageHeading } from './components/page-heading'
import { ScreenContent } from './components/screen-content'
import { useTenderReviewPage } from './use-tender-review-page'
import type { TenderReviewScreen } from './types'

type TenderReviewPageProps = {
  initialScreen?: TenderReviewScreen
}

export function TenderReviewPage({
  initialScreen = 'dashboard',
}: TenderReviewPageProps) {
  const page = useTenderReviewPage(initialScreen)
  const showPageHeading =
    page.screen === 'dashboard' ||
    page.screen === 'create' ||
    page.screen === 'history'

  return (
    <>
      <Header fixed />
      <Main className='space-y-5'>
        {showPageHeading ? (
          <PageHeading
            activeScreen={page.screen}
            onBack={() => page.setScreen(initialScreen)}
          />
        ) : null}
        <ScreenContent page={page} />
      </Main>
    </>
  )
}

export function TenderReviewHistoryPage() {
  return <TenderReviewPage initialScreen='history' />
}

export function TenderReviewDetailPage() {
  const detailView = useSearch({
    from: '/_authenticated/contracts/tender/detail',
    select: (search) => search.view,
  })
  return <TenderReviewPage initialScreen={detailView === 'report' ? 'report' : 'analysis'} />
}
