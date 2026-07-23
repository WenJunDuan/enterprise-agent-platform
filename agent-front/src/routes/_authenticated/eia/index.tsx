import { createFileRoute } from '@tanstack/react-router'
import { EiaSubmitPage } from '@/features/eia/submit-page'

export const Route = createFileRoute('/_authenticated/eia/')({
  component: EiaSubmitPage,
})
