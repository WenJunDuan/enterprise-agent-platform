import { useSearch } from '@tanstack/react-router'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { PageHeading } from './components/page-heading'
import { ScreenContent } from './components/screen-content'
import { useTenderReviewPage } from './use-tender-review-page'
import type { TenderReviewScreen, TenderScenario } from './types'

const TENDER_SCENARIOS: TenderScenario[] = [
  'bidder_self_check',
  'expert_assist',
  'post_eval_monitor',
]

function normalizeTenderScenario(value: unknown): TenderScenario {
  return TENDER_SCENARIOS.includes(value as TenderScenario)
    ? (value as TenderScenario)
    : 'expert_assist'
}

type TenderReviewPageProps = {
  initialScreen?: TenderReviewScreen
  scenario?: TenderScenario
}

export function TenderReviewPage({
  initialScreen = 'dashboard',
  scenario = 'expert_assist',
}: TenderReviewPageProps) {
  const page = useTenderReviewPage(initialScreen, scenario)
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

export function TenderSelfCheckPage() {
  return <TenderReviewPage initialScreen='create' scenario='bidder_self_check' />
}

export function TenderPostEvalMonitorPage() {
  return <TenderReviewPage initialScreen='dashboard' scenario='post_eval_monitor' />
}

export function TenderReviewHistoryPage() {
  return <TenderReviewPage initialScreen='history' />
}

export function TenderReviewDetailPage() {
  const detailSearch = useSearch({
    from: '/_authenticated/contracts/tender/detail',
    select: (search) => ({
      view: search.view,
      scenario: normalizeTenderScenario(search.scenario),
    }),
  })
  return (
    <TenderReviewPage
      initialScreen={detailSearch.view === 'report' ? 'report' : 'analysis'}
      scenario={detailSearch.scenario}
    />
  )
}
