import { createFileRoute } from '@tanstack/react-router'
import { OcrWorkbenchPage } from '@/features/ocr/ocr-workbench-page'

export const Route = createFileRoute('/_authenticated/ocr')({
  component: OcrWorkbenchPage,
})
