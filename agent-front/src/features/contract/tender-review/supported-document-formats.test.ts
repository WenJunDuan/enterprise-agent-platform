import { describe, expect, test } from 'bun:test'
import {
  ACCEPTED_DOCUMENT_FILE_TYPES,
  SUPPORTED_DOCUMENT_EXTENSIONS,
  SUPPORTED_DOCUMENT_FORMAT_GROUPS,
  SUPPORTED_DOCUMENT_FORMATS_VERSION,
} from './supported-document-formats'

describe('supported document format contract', () => {
  test('contains the complete generated upload whitelist', () => {
    expect(SUPPORTED_DOCUMENT_FORMATS_VERSION).toBe(1)
    expect(SUPPORTED_DOCUMENT_FORMAT_GROUPS).toEqual({
      text: ['.txt', '.csv', '.md', '.json', '.tsv'],
      images: ['.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'],
      word_native: ['.docx'],
      word_legacy: ['.doc'],
      excel_ooxml: ['.xlsx', '.xlsm'],
      excel_xls: ['.xls'],
      excel_xlsb: ['.xlsb'],
      presentation_native: ['.pptx'],
      office_convert: ['.ppt', '.odt', '.ods', '.odp'],
      pdf: ['.pdf'],
    })
    expect(SUPPORTED_DOCUMENT_EXTENSIONS).toEqual(
      Object.values(SUPPORTED_DOCUMENT_FORMAT_GROUPS).flat()
    )
  })

  test('accept is extension-only and excludes unsupported image wildcards', () => {
    expect(ACCEPTED_DOCUMENT_FILE_TYPES).toBe(
      SUPPORTED_DOCUMENT_EXTENSIONS.join(',')
    )
    expect(ACCEPTED_DOCUMENT_FILE_TYPES).not.toContain('image/*')
    expect(ACCEPTED_DOCUMENT_FILE_TYPES).not.toContain('.heic')
  })
})
