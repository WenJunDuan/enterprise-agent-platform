import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/settings/appearance')({
  beforeLoad: () => {
    throw redirect({ to: '/settings' })
  },
})
