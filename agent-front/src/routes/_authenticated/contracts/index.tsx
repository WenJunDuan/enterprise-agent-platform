import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/contracts/')({
  beforeLoad: () => {
    throw redirect({ to: '/contracts/tender/list' })
  },
})
