import { createFileRoute } from '@tanstack/react-router'
import { TenderPostEvalMonitorPage } from '@/features/contract/tender-review'

export const Route = createFileRoute('/_authenticated/contracts/tender/post-eval')({
  component: TenderPostEvalMonitorPage,
})
