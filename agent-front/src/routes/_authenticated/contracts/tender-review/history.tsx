import { createFileRoute } from '@tanstack/react-router'
import { TenderReviewHistoryPage } from '@/features/contract/tender-review'

export const Route = createFileRoute(
  '/_authenticated/contracts/tender-review/history'
)({
  component: TenderReviewHistoryPage,
})
