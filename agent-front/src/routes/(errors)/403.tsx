import { z } from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { ForbiddenError } from '@/features/errors/forbidden'

const searchSchema = z.object({
  redirect: z.string().optional(),
  message: z.string().optional(),
})

export const Route = createFileRoute('/(errors)/403')({
  validateSearch: searchSchema,
  component: RouteComponent,
})

// eslint-disable-next-line react-refresh/only-export-components
function RouteComponent() {
  const { message, redirect } = Route.useSearch()

  return (
    <ForbiddenError
      autoRedirectToAuth={Boolean(message)}
      message={message}
      redirect={redirect}
    />
  )
}
