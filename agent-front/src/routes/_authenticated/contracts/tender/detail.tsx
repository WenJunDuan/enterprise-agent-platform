import { createFileRoute } from '@tanstack/react-router'
import { TenderReviewDetailPage } from '@/features/contract/tender-review'

export const Route = createFileRoute('/_authenticated/contracts/tender/detail')({
  validateSearch: (search: Record<string, unknown>) => ({
    view: search.view === 'report' ? 'report' : 'analysis',
  }),
  component: TenderReviewDetailPage,
})
