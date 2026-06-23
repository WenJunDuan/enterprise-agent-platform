import { describe, expect, test } from 'bun:test'
import { tenderReviewMockData } from './mock-data'
import {
  buildDashboardSummary,
  buildTenderReviewData,
  filterReviewHistory,
  mapTenderProject,
} from './model'
import type { TenderReviewMockData } from './types'

describe('contract tender review model', () => {
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
              },
              {
                item: '技术方案',
                max: 30,
                scoring_rule: '按技术方案完整性评分。',
                source_ref: '招标文件 p.18',
                tag: 'scored',
                category: '技术标',
              },
              {
                item: '价格分',
                max: 40,
                scoring_rule: '最低有效报价/本报价×40。',
                source_ref: '招标文件 p.20',
                tag: 'requires_cross_bid_comparison',
                score_mode: 'formula',
                category: '商务标',
              },
            ],
          },
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
              price_score: 38,
              other_score: 51,
              total_score: 89,
              rank: 1,
              status: 'scored',
            },
            {
              claim_id: '中铁二局',
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
    expect(data.reviewBidders.map((bidder) => [bidder.name, bidder.total])).toEqual([
      ['中建一局', 89],
      ['中铁二局', 86],
    ])
    expect(data.categories[0]?.items[0]).toMatchObject({
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
      ])
    ).toEqual([
      ['企业实力', 6, 6, 'business'],
      ['技术方案', 27, 30, 'technical'],
      ['价格分', null, 40, 'business'],
    ])
    expect(data.scoreSummary?.pendingItems[0]).toMatchObject({
      item: '价格分',
      deduction: null,
      basis: '需横比所有投标报价后计算价格分。',
    })
    expect(data.resultPolicyRefs?.[0]).toEqual({
      id: 'tender_evalmethod_004',
      name: '综合评估法',
      sourceText: '评标委员会应按招标文件规定的评标标准和方法评审。',
    })
    expect(data.paragraphs[0]?.text).toContain('施工组织设计覆盖关键工序')
    expect(data.compareGroups[0]?.rows.map((row) => row.cells)).toEqual([
      [38, 36],
      [51, 50],
    ])
    expect(
      data.compareScoreRows
        ?.find((row) => row.item === '技术方案')
        ?.cells.map((cell) => cell.score)
    ).toEqual([27, 25])
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
            bidder_name: '南通新和科技有限公司',
            status: 'completed',
            verdict: 'manual_review',
          },
          {
            request_id: 'req-b',
            claim_id: '91320602MA1X9Y5678',
            bidder_name: '江苏云桥工程有限公司',
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
          bidder_name: '南通新和科技有限公司',
          verdict: 'manual_review',
        },
        {
          request_id: 'req-b',
          claim_id: '91320602MA1X9Y5678',
          bidder_name: '江苏云桥工程有限公司',
          verdict: 'manual_review',
        },
      ],
      selectedResult: {
        claim_id: '91320602MA1X9Y1234',
        verdict: 'manual_review',
        explanation: '需横比后确认价格分。',
        extracted_data: {
          bidder: {
            name: '南通新和科技有限公司',
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
              name: '江苏云桥工程有限公司',
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
      '南通新和科技有限公司',
      '江苏云桥工程有限公司',
    ])
    expect(
      data.compareScoreRows
        ?.find((row) => row.item === '企业实力')
        ?.cells.map((cell) => cell.bidderName)
    ).toEqual(['南通新和科技有限公司', '江苏云桥工程有限公司'])
    expect(data.paragraphs[0]).toMatchObject({
      label: '投标文件【第315页】',
    })
  })
})
