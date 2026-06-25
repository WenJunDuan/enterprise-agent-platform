import { describe, expect, test } from 'bun:test'
import { tenderReviewMockData } from './mock-data'
import {
  buildDashboardSummary,
  buildTenderReviewData,
  deriveReviewDimension,
  filterReviewHistory,
  mapTenderProject,
} from './model'
import type { TenderReviewMockData } from './types'

describe('contract tender review model', () => {
  test('deriveReviewDimension prioritizes structured price signals', () => {
    expect(
      deriveReviewDimension(
        { item: '评标基准价得分' },
        { item: '评标基准价得分', tag: 'requires_cross_bid_comparison' }
      )
    ).toBe('price')
    expect(
      deriveReviewDimension(
        { item: '报价测算', score_mode: 'formula' },
        { item: '报价测算', evaluator_type: 'objective' }
      )
    ).toBe('price')
    expect(deriveReviewDimension({ item: '投标报价' })).toBe('price')
  })

  test('deriveReviewDimension identifies subjective technical review', () => {
    expect(
      deriveReviewDimension(
        { item: '技术方案' },
        { item: '技术方案', evaluator_type: 'subjective' }
      )
    ).toBe('technical_subjective')
    expect(
      deriveReviewDimension(
        { item: '施工组织设计' },
        { item: '施工组织设计', evaluator_type: 'mixed' }
      )
    ).toBe('technical_subjective')
  })

  test('deriveReviewDimension keeps objective and unknown legacy data in business objective', () => {
    expect(
      deriveReviewDimension(
        { item: '企业业绩', score_mode: 'additive' },
        { item: '企业业绩', evaluator_type: 'objective' }
      )
    ).toBe('business_objective')
    expect(
      deriveReviewDimension(
        { item: '质保服务', score_mode: 'banded' },
        { item: '质保服务', evaluator_type: 'objective' }
      )
    ).toBe('business_objective')
    expect(deriveReviewDimension({ item: '技术方案' })).toBe(
      'business_objective'
    )
  })

  test('buildDashboardSummary aggregates prototype workbench counts', () => {
    const summary = buildDashboardSummary(tenderReviewMockData)

    expect(summary.totalCount).toBe(tenderReviewMockData.projects.length)
    expect(summary.activeCount).toBe(3)
    expect(summary.reviewCount).toBe(1)
    expect(summary.completedCount).toBe(3)
    expect(summary.stats.map((stat) => [stat.label, stat.count])).toEqual([
      ['分析中', 2],
      ['待复核', 1],
      ['已完成', 3],
      ['全部项目', 6],
    ])
    expect(summary.activeProjects.map((project) => project.code)).toEqual([
      'BJ-2026-ZB-018',
      'BJ-2026-ZB-014',
      'BJ-2026-ZB-011',
    ])
  })

  test('buildDashboardSummary handles empty project data', () => {
    const emptyData: TenderReviewMockData = {
      ...tenderReviewMockData,
      projects: [],
    }

    const summary = buildDashboardSummary(emptyData)

    expect(summary.totalCount).toBe(0)
    expect(summary.activeProjects).toEqual([])
    expect(summary.stats.map((stat) => stat.count)).toEqual([0, 0, 0, 0])
  })

  test('filterReviewHistory only returns completed projects', () => {
    const allHistory = filterReviewHistory(tenderReviewMockData.projects, {
      query: '',
      timeRange: 'all',
      now: '2026-06-19',
    })

    expect(allHistory.map((item) => item.status)).toEqual([
      'done',
      'done',
      'done',
    ])
  })

  test('filterReviewHistory applies search and time range filters', () => {
    const searchResult = filterReviewHistory(tenderReviewMockData.projects, {
      query: '轨道交通',
      timeRange: 'all',
      now: '2026-06-19',
    })
    const completedThisMonth = filterReviewHistory(
      tenderReviewMockData.projects,
      {
        query: '',
        timeRange: 'month',
        now: '2026-06-19',
      }
    )
    const weekItems = filterReviewHistory(tenderReviewMockData.projects, {
      query: '',
      timeRange: 'week',
      now: '2026-06-19',
    })

    expect(searchResult.map((item) => item.code)).toEqual(['BJ-2026-ZB-009'])
    expect(completedThisMonth.map((item) => item.code)).toEqual([
      'BJ-2026-ZB-009',
      'BJ-2026-ZB-006',
    ])
    expect(weekItems).toEqual([])
  })

  test('mapTenderProject derives tender-review project fields from backend detail and compare', () => {
    const project = mapTenderProject(
      {
        project_id: 'project-1',
        tender_no: 'WX-2026-001',
        title: '无锡市政管廊施工项目',
        tenderee: '无锡城投',
        method: '综合评估法',
        control_price: '120000000',
        funding_type: 'state_funded',
        status: 'done',
        created_at: '2026-06-20T02:30:00+00:00',
        updated_at: '2026-06-20T06:30:00+00:00',
        bidder_count: 2,
        bids: [
          {
            request_id: 'req-a',
            claim_id: '中建一局',
            status: 'completed',
            verdict: 'approved',
          },
          {
            request_id: 'req-b',
            claim_id: '中铁二局',
            status: 'completed',
            verdict: 'manual_review',
          },
        ],
        recommended_bidder: '中建一局',
        compare_stale: false,
      },
      {
        project_id: 'project-1',
        result: {
          project_id: 'project-1',
          bidders: [
            {
              claim_id: '中建一局',
              price_score: 38,
              other_score: 51,
              total_score: 89,
              rank: 1,
              status: 'scored',
            },
          ],
          recommended: '中建一局',
          provisional: false,
          warnings: [],
          explanation: '推荐排名第一投标人。',
          policy_refs: [],
        },
        stale: false,
        computed_at: '2026-06-20T07:00:00+00:00',
        input_result_ids: ['req-a', 'req-b'],
      }
    )

    expect(project).toEqual({
      id: 'project-1',
      name: '无锡市政管廊施工项目',
      code: 'WX-2026-001',
      method: '综合评估法',
      bidderCount: 2,
      score: '89',
      date: '2026-06-20',
      status: 'done',
      stage: '已完成',
      progress: 100,
      riskCount: 1,
      recommendedBidder: '中建一局',
    })
  })

  test('buildTenderReviewData maps backend result and compare payloads into analysis/report data', () => {
    const data = buildTenderReviewData({
      project: {
        project_id: 'project-1',
        tender_no: 'WX-2026-001',
        title: '无锡市政管廊施工项目',
        tenderee: null,
        method: '综合评估法',
        control_price: '120000000',
        funding_type: 'state_funded',
        status: 'done',
        created_at: '2026-06-20T02:30:00+00:00',
        updated_at: '2026-06-20T06:30:00+00:00',
        bidder_count: 2,
        bids: [
          {
            request_id: 'req-a',
            claim_id: '中建一局',
            status: 'completed',
            verdict: 'approved',
          },
          {
            request_id: 'req-b',
            claim_id: '中铁二局',
            status: 'completed',
            verdict: 'approved',
          },
        ],
        recommended_bidder: '中建一局',
        compare_stale: false,
      },
      resultSummaries: [
        {
          request_id: 'req-a',
          claim_id: '中建一局',
          verdict: 'approved',
          manual_review_reason: null,
          created_at: '2026-06-20T06:00:00+00:00',
        },
      ],
      selectedResult: {
        claim_id: '中建一局',
        verdict: 'approved',
        explanation: '资格和技术响应满足招标要求。',
        extracted_data: {
          criteria: {
            method: '综合评估法',
            items: [
              {
                item: '企业实力',
                max: 6,
                scoring_rule: '按企业资质和证书评分。',
                source_ref: '招标文件 p.16',
                tag: 'scored',
                category: '商务标',
                evaluator_type: 'objective',
              },
              {
                item: '技术方案',
                max: 30,
                scoring_rule: '按技术方案完整性评分。',
                source_ref: '招标文件 p.18',
                tag: 'scored',
                category: '技术标',
                evaluator_type: 'subjective',
              },
              {
                item: '价格分',
                max: 40,
                scoring_rule: '最低有效报价/本报价×40。',
                source_ref: '招标文件 p.20',
                tag: 'requires_cross_bid_comparison',
                score_mode: 'formula',
                category: '商务标',
                evaluator_type: 'objective',
              },
            ],
          },
          eligibility_checks: [
            {
              rule_id: 'q1',
              check: '企业资质证书',
              status: 'pass',
              basis: '已提供有效企业资质证书。',
              evidence: {
                source: '投标文件 p.8',
                quote: '建筑工程施工总承包一级',
              },
            },
          ],
          scoring: [
            {
              item: '企业实力',
              max: 6,
              score: 6,
              status: 'scored',
              score_mode: 'additive',
              category: '商务标',
              basis: '企业资质证书齐全。',
            },
            {
              item: '技术方案',
              max: 30,
              score: 27,
              status: 'scored',
              score_mode: 'banded',
              category: '技术标',
              basis: '施工组织设计完整。',
              selected_band: {
                level: '良',
                points: 27,
                reason: '主要章节完整，细节略有缺失。',
              },
            },
            {
              item: '价格分',
              max: 40,
              score: null,
              status: 'manual_review',
              score_mode: 'formula',
              category: '商务标',
              basis: '需横比所有投标报价后计算价格分。',
            },
          ],
        },
        evidence_chain: [
          {
            source: '投标文件 p.20',
            finding: '施工组织设计覆盖关键工序。',
            conclusion: '技术方案可得分。',
          },
        ],
        policy_refs: [
          {
            rule_id: 'tender_evalmethod_004',
            name: '综合评估法',
            source_text: '评标委员会应按招标文件规定的评标标准和方法评审。',
          },
        ],
      },
      resultDetails: [
        {
          claim_id: '中铁二局',
          verdict: 'approved',
          explanation: '资格和技术响应满足招标要求。',
          extracted_data: {
            scoring: [
              {
                item: '企业实力',
                max: 6,
                score: 5,
                status: 'scored',
                score_mode: 'additive',
                category: '商务标',
                basis: '企业证书少 1 项。',
              },
              {
                item: '技术方案',
                max: 30,
                score: 25,
                status: 'scored',
                score_mode: 'banded',
                category: '技术标',
                basis: '施工组织设计可行，进度措施略弱。',
              },
              {
                item: '价格分',
                max: 40,
                score: null,
                status: 'manual_review',
                score_mode: 'formula',
                category: '商务标',
                basis: '需横比所有投标报价后计算价格分。',
              },
            ],
          },
          evidence_chain: [],
        },
      ],
      compare: {
        project_id: 'project-1',
        result: {
          project_id: 'project-1',
          bidders: [
            {
              claim_id: '中建一局',
              bid_price: { amount: 1000000, currency: 'CNY' },
              price_score: 38,
              other_score: 51,
              total_score: 89,
              rank: 1,
              status: 'scored',
            },
            {
              claim_id: '中铁二局',
              bid_price: { amount: 1055555, currency: 'CNY' },
              price_score: 36,
              other_score: 50,
              total_score: 86,
              rank: 2,
              status: 'scored',
            },
          ],
          recommended: '中建一局',
          provisional: false,
          warnings: ['有效投标人数量为 2，建议复核竞争性。'],
          explanation: '中建一局综合排名第一。',
          policy_refs: ['tender_evalmethod_004'],
          evidence_chain: [
            {
              source: '横比计算',
              finding: '价格分公式：最低有效报价/本投标报价×40。',
              conclusion: '中建一局价格分 38 分，中铁二局价格分 36 分。',
            },
          ],
        },
        stale: false,
        computed_at: '2026-06-20T07:00:00+00:00',
        input_result_ids: ['req-a', 'req-b'],
      },
    })

    expect(data.projectInfo).toMatchObject({
      name: '无锡市政管廊施工项目',
      code: 'WX-2026-001',
      method: '综合评估法',
      controlPrice: '120000000',
    })
    expect(
      data.reviewBidders.map((bidder) => [bidder.name, bidder.total])
    ).toEqual([
      ['中建一局', 89],
      ['中铁二局', 86],
    ])
    // D6：报告类目按招标文件实际要素（criteria/scoring.category）动态分栏——
    // 资格审查恒首位，其余按标书出现顺序、用标书原始类目名作小标题（有几类显示几类）。
    expect(data.categories.map((c) => [c.key, c.label])).toEqual([
      ['qual', '资格审查'],
      ['商务标', '商务标'],
      ['技术标', '技术标'],
    ])
    expect(data.categories[0]?.items[0]).toMatchObject({
      title: '资格审查：企业资质证书',
      status: 'pass',
    })
    expect(data.categories[1]?.items.map((item) => item.title)).toEqual([
      '企业实力',
      '价格分',
    ])
    expect(data.categories[2]?.items[0]).toMatchObject({
      title: '技术方案',
      got: 27,
      max: 30,
      status: 'pass',
    })
    expect(
      data.scoringItems?.map((item) => [
        item.item,
        item.score,
        item.max,
        item.scoreCategory,
        item.reviewDimension,
      ])
    ).toEqual([
      ['企业实力', 6, 6, 'business', 'business_objective'],
      ['技术方案', 27, 30, 'technical', 'technical_subjective'],
      ['价格分', null, 40, 'business', 'price'],
    ])
    expect(data.scoreSummary?.pendingItems[0]).toMatchObject({
      item: '价格分',
      deduction: null,
      basis: '需横比所有投标报价后计算价格分。',
    })
    expect(data.scoreSummary).toMatchObject({
      maxTotal: 76,
      earnedTotal: 33,
      deductedTotal: 3,
      pendingTotal: 40,
    })
    expect(data.scoreSummary?.deductedItems.map((item) => item.item)).toEqual([
      '技术方案',
    ])
    expect(data.scoreSummary?.pendingItems.map((item) => item.item)).toEqual([
      '价格分',
    ])
    expect(data.resultPolicyRefs?.[0]).toEqual({
      id: 'tender_evalmethod_004',
      name: '综合评估法',
      sourceText: '评标委员会应按招标文件规定的评标标准和方法评审。',
    })
    expect(data.resultEligibilityChecks?.[0]).toMatchObject({
      check: '企业资质证书',
      status: 'pass',
    })
    expect(data.paragraphs[0]?.text).toContain('建筑工程施工总承包一级')
    expect(data.paragraphs[1]?.text).toContain('施工组织设计覆盖关键工序')
    expect(data.compareGroups[0]?.rows.map((row) => row.cells)).toEqual([
      [38, 36],
      [51, 50],
    ])
    expect(data.comparePriceDetail).toMatchObject({
      formula: '价格分公式：最低有效报价/本投标报价×40。；中建一局价格分 38 分，中铁二局价格分 36 分。',
      cells: [
        { bidderName: '中建一局', bidPrice: '1,000,000 CNY', score: 38 },
        { bidderName: '中铁二局', bidPrice: '1,055,555 CNY', score: 36 },
      ],
    })
    expect(
      data.compareScoreRows
        ?.find((row) => row.item === '技术方案')
    ).toMatchObject({
      reviewDimension: 'technical_subjective',
      cells: [
        { score: 27, basis: '施工组织设计完整。' },
        { score: 25, basis: '施工组织设计可行，进度措施略弱。' },
      ],
    })
    expect(data.compareNotice?.warnings).toEqual([
      '有效投标人数量为 2，建议复核竞争性。',
    ])
  })

  test('buildTenderReviewData displays enterprise names instead of credit-code claim ids', () => {
    const data = buildTenderReviewData({
      project: {
        project_id: 'project-credit-code',
        tender_no: 'JSZC-2026-001',
        title: '智慧园区采购项目',
        tenderee: null,
        method: '综合评估法',
        control_price: '5000000',
        funding_type: 'state_funded',
        status: 'done',
        created_at: '2026-06-20T02:30:00+00:00',
        updated_at: '2026-06-20T06:30:00+00:00',
        bidder_count: 2,
        bids: [
          {
            request_id: 'req-a',
            claim_id: '91320602MA1X9Y1234',
            bidder_name: '投标人XH',
            status: 'completed',
            verdict: 'manual_review',
          },
          {
            request_id: 'req-b',
            claim_id: '91320602MA1X9Y5678',
            bidder_name: '投标人YQ',
            status: 'completed',
            verdict: 'manual_review',
          },
        ],
        recommended_bidder: null,
        compare_stale: false,
      },
      resultSummaries: [
        {
          request_id: 'req-a',
          claim_id: '91320602MA1X9Y1234',
          bidder_name: '投标人XH',
          verdict: 'manual_review',
        },
        {
          request_id: 'req-b',
          claim_id: '91320602MA1X9Y5678',
          bidder_name: '投标人YQ',
          verdict: 'manual_review',
        },
      ],
      selectedResult: {
        claim_id: '91320602MA1X9Y1234',
        verdict: 'manual_review',
        explanation: '需横比后确认价格分。',
        extracted_data: {
          bidder: {
            name: '投标人XH',
            credit_code: '91320602MA1X9Y1234',
            legal_rep: '张三',
          },
          scoring: [
            {
              item: '企业实力',
              max: 6,
              score: 6,
              status: 'scored',
              basis: '企业资质证书齐全。',
              evidence: {
                source: '投标文件【第315页】',
                quote: '企业资质证书齐全',
              },
            },
          ],
        },
        evidence_chain: [
          {
            source: '投标文件【第315页】',
            finding: '企业资质证书齐全。',
            conclusion: '企业实力可得 6 分。',
          },
        ],
      },
      resultDetails: [
        {
          claim_id: '91320602MA1X9Y5678',
          verdict: 'manual_review',
          explanation: '需横比后确认价格分。',
          extracted_data: {
            bidder: {
              name: '投标人YQ',
              credit_code: '91320602MA1X9Y5678',
              legal_rep: '李四',
            },
            scoring: [
              {
                item: '企业实力',
                max: 6,
                score: 5,
                status: 'scored',
                basis: '缺少 1 项证书。',
              },
            ],
          },
        },
      ],
      compare: {
        project_id: 'project-credit-code',
        result: {
          project_id: 'project-credit-code',
          bidders: [
            {
              claim_id: '91320602MA1X9Y1234',
              price_score: 30,
              other_score: 45,
              total_score: 75,
              rank: 1,
              status: 'manual_review',
            },
            {
              claim_id: '91320602MA1X9Y5678',
              price_score: 29,
              other_score: 44,
              total_score: 73,
              rank: 2,
              status: 'manual_review',
            },
          ],
          recommended: null,
          provisional: true,
          warnings: [],
          policy_refs: [],
        },
        stale: false,
      },
    })

    expect(data.reviewBidders.map((bidder) => bidder.name)).toEqual([
      '投标人XH',
      '投标人YQ',
    ])
    expect(
      data.compareScoreRows
        ?.find((row) => row.item === '企业实力')
        ?.cells.map((cell) => cell.bidderName)
    ).toEqual(['投标人XH', '投标人YQ'])
    expect(data.paragraphs[0]).toMatchObject({
      label: '投标文件【第315页】',
    })
  })

  test('buildTenderReviewData ranks bidder tabs by total score without compare', () => {
    const data = buildTenderReviewData({
      project: {
        project_id: 'project-no-compare',
        tender_no: 'TZ-2026-001',
        title: '通州区建设项目',
        tenderee: '通州城投',
        method: '综合评估法',
        control_price: '1000000',
        funding_type: 'state_funded',
        status: 'done',
        created_at: '2026-06-24T02:30:00+08:00',
        updated_at: '2026-06-24T03:30:00+08:00',
        bidder_count: 2,
        bids: [
          {
            request_id: 'req-a',
            claim_id: '投标人TZ',
            bidder_name: '投标人TZ',
            status: 'completed',
            verdict: 'manual_review',
          },
          {
            request_id: 'req-b',
            claim_id: '投标人TS',
            bidder_name: '投标人TS',
            status: 'completed',
            verdict: 'manual_review',
          },
        ],
        recommended_bidder: null,
        compare_stale: false,
      },
      resultSummaries: [
        {
          request_id: 'req-a',
          claim_id: '投标人TZ',
          bidder_name: '投标人TZ',
          verdict: 'manual_review',
        },
        {
          request_id: 'req-b',
          claim_id: '投标人TS',
          bidder_name: '投标人TS',
          verdict: 'manual_review',
        },
      ],
      selectedResult: {
        request_id: 'req-b',
        claim_id: '投标人TS',
        verdict: 'manual_review',
        explanation: '第二家当前详情。',
        extracted_data: {
          scoring: [
            {
              item: '商务标',
              max: 10,
              score: 7.1,
              status: 'scored',
              basis: '第二家商务标得 7.1 分。',
            },
          ],
        },
      },
      resultDetails: [
        {
          request_id: 'req-a',
          claim_id: '投标人TZ',
          verdict: 'manual_review',
          explanation: '第一家详情。',
          extracted_data: {
            scoring: [
              {
                item: '商务标',
                max: 5,
                score: 5,
                status: 'scored',
                basis: '第一家商务标得 5 分。',
              },
            ],
          },
        },
      ],
      compare: null,
    })

    expect(
      data.reviewBidders.map((bidder) => [
        bidder.rank,
        bidder.name,
        bidder.total,
      ])
    ).toEqual([
      [1, '投标人TS', 7.1],
      [2, '投标人TZ', 5],
    ])
    expect(data.scoringItems?.[0]).toMatchObject({
      item: '商务标',
      score: 7.1,
      basis: '第二家商务标得 7.1 分。',
    })
  })
})
