import { createFileRoute } from '@tanstack/react-router'
import { AuditTaskDetailPage } from '@/features/audit/audit-task-detail-page'

export const Route = createFileRoute('/_authenticated/audit/tasks/$taskId')({
  component: RouteComponent,
})

// eslint-disable-next-line react-refresh/only-export-components
function RouteComponent() {
  const { taskId } = Route.useParams()
  return <AuditTaskDetailPage taskId={taskId} />
}
