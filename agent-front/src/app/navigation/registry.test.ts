import { describe, expect, test } from 'bun:test'
import { buildNavigationGroups, getBreadcrumbsForPath } from './registry'

describe('navigation registry', () => {
  test('orders tender audit before reimbursement and OCR menus', () => {
    const groups = buildNavigationGroups(null)

    expect(groups.map((group) => group.title)).toEqual([
      '智能招投标审核',
      '智能报销审核',
      '智能 OCR',
    ])
  })

  test('renames reimbursement audit group and entry', () => {
    const groups = buildNavigationGroups(null)
    const reimbursementGroup = groups.find(
      (group) => group.title === '智能报销审核'
    )

    expect(reimbursementGroup?.items.map((item) => item.title)).toEqual([
      '报销审核',
    ])
    expect(reimbursementGroup?.items.map((item) => item.url)).toEqual([
      '/audit',
    ])
  })

  test('keeps tender review and history under the intelligent tender audit menu', () => {
    const groups = buildNavigationGroups(null)
    const tenderGroup = groups.find(
      (group) => group.title === '智能招投标审核'
    )

    expect(tenderGroup?.items.map((item) => item.title)).toEqual([
      '项目管理',
      '历史评审',
    ])
    expect(tenderGroup?.items.map((item) => item.url)).toEqual([
      '/contracts/tender-review',
      '/contracts/tender-review/history',
    ])
  })

  test('renames OCR group while keeping OCR entry title', () => {
    const groups = buildNavigationGroups(null)
    const ocrGroup = groups.find((group) => group.title === '智能 OCR')

    expect(ocrGroup?.items.map((item) => item.title)).toEqual(['OCR 识别'])
    expect(ocrGroup?.items.map((item) => item.url)).toEqual(['/ocr'])
  })

  test('uses tender breadcrumbs for tender routes', () => {
    expect(getBreadcrumbsForPath('/contracts')).toEqual([
      { label: '智能招投标审核' },
      { label: '项目管理' },
    ])
    expect(getBreadcrumbsForPath('/contracts/tender-review')).toEqual([
      { label: '智能招投标审核' },
      { label: '项目管理' },
    ])
    expect(getBreadcrumbsForPath('/contracts/tender-review/history')).toEqual([
      { label: '智能招投标审核' },
      { label: '历史评审' },
    ])
  })

  test('uses reimbursement and OCR breadcrumbs for existing routes', () => {
    expect(getBreadcrumbsForPath('/audit')).toEqual([
      { label: '智能报销审核' },
      { label: '报销审核' },
    ])
    expect(getBreadcrumbsForPath('/audit/submit')).toEqual([
      { label: '智能报销审核' },
      { label: '报销审核', href: '/audit' },
      { label: '新建报销审核' },
    ])
    expect(getBreadcrumbsForPath('/ocr')).toEqual([
      { label: '智能 OCR' },
      { label: 'OCR 识别' },
    ])
  })
})
