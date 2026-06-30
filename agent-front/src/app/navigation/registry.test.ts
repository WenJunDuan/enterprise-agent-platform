import { describe, expect, test } from 'bun:test'
import {
  buildNavigationGroups,
  getBreadcrumbsForPath,
  getNavigationMenuDefinitions,
} from './registry'
import {
  getEnabledTenderScenarios,
  parseEnabledTenderScenarios,
} from './tender-scenarios'

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
      '专家辅助',
      '历史评审',
    ])
    expect(tenderGroup?.items.map((item) => item.url)).toEqual([
      '/contracts/tender/list',
      '/contracts/tender/history',
    ])
  })

  test('defaults navigation scenarios to expert assist only', () => {
    expect(parseEnabledTenderScenarios(undefined)).toEqual(['expert_assist'])
    expect(getEnabledTenderScenarios({})).toEqual(['expert_assist'])
  })

  test('shows three tender scenario entries when enabled', () => {
    const groups = buildNavigationGroups(null, undefined, undefined, [
      'bidder_self_check',
      'expert_assist',
      'post_eval_monitor',
    ])
    const tenderGroup = groups.find(
      (group) => group.title === '智能招投标审核'
    )

    expect(tenderGroup?.items.map((item) => item.title)).toEqual([
      '投标自查',
      '专家辅助',
      '评后监督',
      '历史评审',
    ])
    expect(tenderGroup?.items.map((item) => item.url)).toEqual([
      '/contracts/tender/self-check',
      '/contracts/tender/list',
      '/contracts/tender/post-eval',
      '/contracts/tender/history',
    ])
  })

  test('renames OCR group while keeping OCR entry title', () => {
    const groups = buildNavigationGroups(null)
    const ocrGroup = groups.find((group) => group.title === '智能 OCR')

    expect(ocrGroup?.items.map((item) => item.title)).toEqual(['OCR 识别'])
    expect(ocrGroup?.items.map((item) => item.url)).toEqual(['/ocr'])
  })

  test('can hide an entire sidebar menu group', () => {
    const groups = buildNavigationGroups(null, undefined, {
      groups: {
        '智能 OCR': false,
      },
      items: {},
    })

    expect(groups.map((group) => group.title)).toEqual([
      '智能招投标审核',
      '智能报销审核',
    ])
  })

  test('can hide a single sidebar menu item', () => {
    const groups = buildNavigationGroups(null, undefined, {
      groups: {},
      items: {
        '智能招投标审核:/contracts/tender/history': false,
      },
    })
    const tenderGroup = groups.find(
      (group) => group.title === '智能招投标审核'
    )

    expect(tenderGroup?.items.map((item) => item.title)).toEqual(['专家辅助'])
  })

  test('exposes the unfiltered sidebar menu definitions for management controls', () => {
    const groups = getNavigationMenuDefinitions()

    expect(groups.map((group) => group.title)).toEqual([
      '智能招投标审核',
      '智能报销审核',
      '智能 OCR',
    ])
  })

  test('uses tender breadcrumbs for tender routes', () => {
    expect(getBreadcrumbsForPath('/contracts')).toEqual([
      { label: '智能招投标审核' },
      { label: '评审列表' },
    ])
    expect(getBreadcrumbsForPath('/contracts/tender/list')).toEqual([
      { label: '智能招投标审核' },
      { label: '专家辅助' },
    ])
    expect(getBreadcrumbsForPath('/contracts/tender/history')).toEqual([
      { label: '智能招投标审核' },
      { label: '历史评审' },
    ])
    expect(getBreadcrumbsForPath('/contracts/tender/detail')).toEqual([
      { label: '智能招投标审核' },
      { label: '专家辅助', href: '/contracts/tender/list' },
      { label: '分析中心' },
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
