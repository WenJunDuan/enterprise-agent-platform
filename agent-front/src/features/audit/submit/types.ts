import type { AttachmentCategory } from '../types'

export interface SelectedAttachment {
  id: string
  file: File
  category: AttachmentCategory
}
