import { createFileRoute } from '@tanstack/react-router'
import { ContractReviewPage } from '@/features/contract/contract-review-page'

export const Route = createFileRoute('/_authenticated/contracts')({
  component: ContractReviewPage,
})
