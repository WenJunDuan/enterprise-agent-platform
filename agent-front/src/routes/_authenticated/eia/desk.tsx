import { createFileRoute } from '@tanstack/react-router'
import { EiaDeskPage } from '@/features/eia/desk-page'

export const Route = createFileRoute('/_authenticated/eia/desk')({
  component: EiaDeskPage,
})
