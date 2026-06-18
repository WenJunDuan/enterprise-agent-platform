import { createFileRoute } from '@tanstack/react-router'
import { AuditTasksPage } from '@/features/audit/audit-tasks-page'

export const Route = createFileRoute('/_authenticated/audit/')({
  component: AuditTasksPage,
})
