import { createFileRoute } from '@tanstack/react-router'
import { TenderSelfCheckPage } from '@/features/contract/tender-review'

export const Route = createFileRoute('/_authenticated/contracts/tender/self-check')({
  component: TenderSelfCheckPage,
})
