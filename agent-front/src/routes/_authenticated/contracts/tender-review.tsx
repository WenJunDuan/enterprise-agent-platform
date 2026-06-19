import { Outlet, createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/contracts/tender-review')(
  {
    component: Outlet,
  }
)
