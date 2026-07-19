import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'
import { AnalysisWorkbenchView } from './analysis-workbench-view'
import type { TenderReviewMockData } from '../types'

describe('AnalysisWorkbenchView null guards', () => {
  test('renders incomplete review data without undefined or NaN output', () => {
    const incompleteData = {
      projects: [],
      projectInfo: undefined,
      tenderFiles: [],
      uploadBidders: [],
      reviewBidders: undefined,
      categories: [
        {
          key: 'qual',
          label: undefined,
          items: [
            {
              id: 'missing-fields',
              title: undefined,
              desc: undefined,
              loc: undefined,
              aiNote: undefined,
              max: Number.NaN,
              got: undefined,
              status: undefined,
            },
          ],
        },
      ],
      paragraphs: undefined,
      compareGroups: [],
      scoringItems: undefined,
      overviewChecklist: undefined,
      bidderCards: undefined,
    } as unknown as TenderReviewMockData

    const markup = renderToStaticMarkup(
      createElement(AnalysisWorkbenchView, {
        data: incompleteData,
        mode: 'detail',
        category: 'qual',
        selectedBidderId: '',
        activeItemId: 'missing-fields',
        onMode: () => {},
        onCategory: () => {},
        onBidder: () => {},
        onActiveItem: () => {},
        onHistory: () => {},
        onReport: () => {},
      })
    )

    expect(markup).not.toContain('undefined')
    expect(markup).not.toContain('NaN')
    expect(markup).toContain('定位原文 · —')
  })
})
