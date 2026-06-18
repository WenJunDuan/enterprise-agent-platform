import { createFileRoute } from '@tanstack/react-router'
import { AuditSubmitPage } from '@/features/audit/audit-submit-page'

export const Route = createFileRoute('/_authenticated/audit/submit')({
  component: AuditSubmitPage,
})
