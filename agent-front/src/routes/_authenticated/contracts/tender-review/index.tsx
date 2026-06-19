import { createFileRoute } from '@tanstack/react-router'
import { TenderReviewPage } from '@/features/contract/tender-review'

export const Route = createFileRoute(
  '/_authenticated/contracts/tender-review/'
)({
  component: TenderReviewPage,
})
