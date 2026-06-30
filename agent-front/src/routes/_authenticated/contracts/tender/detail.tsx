import { createFileRoute } from '@tanstack/react-router'
import { TenderReviewDetailPage } from '@/features/contract/tender-review'
import type { TenderScenario } from '@/features/contract/tender-review/types'

const TENDER_SCENARIOS: TenderScenario[] = [
  'bidder_self_check',
  'expert_assist',
  'post_eval_monitor',
]

function parseTenderScenario(value: unknown): TenderScenario {
  return TENDER_SCENARIOS.includes(value as TenderScenario)
    ? (value as TenderScenario)
    : 'expert_assist'
}

export const Route = createFileRoute('/_authenticated/contracts/tender/detail')({
  validateSearch: (search: Record<string, unknown>) => ({
    view: search.view === 'report' ? 'report' : 'analysis',
    scenario: parseTenderScenario(search.scenario),
  }),
  component: TenderReviewDetailPage,
})
