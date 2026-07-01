import { describe, expect, test } from 'bun:test'
import { tenderReviewMockData } from './mock-data'
import {
  buildDashboardSummary,
  buildIssueList,
  buildOverviewChecklist,
  buildTenderReviewData,
  deriveReviewDimension,
  filterReviewHistory,
  getAdvisoryLabel,
  mapTenderProject,
} from './model'
import type { AuditResult } from '@/features/audit/types'
import type { ChecklistItem, TenderReviewMockData } from './types'

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
            claim_id: '江苏通州二建',
            bidder_name: '江苏通州二建',
            status: 'completed',
            verdict: 'manual_review',
          },
          {
            request_id: 'req-b',
            claim_id: '江苏通州四建',
            bidder_name: '江苏通州四建',
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
          claim_id: '江苏通州二建',
          bidder_name: '江苏通州二建',
          verdict: 'manual_review',
        },
        {
          request_id: 'req-b',
          claim_id: '江苏通州四建',
          bidder_name: '江苏通州四建',
          verdict: 'manual_review',
        },
      ],
      selectedResult: {
        request_id: 'req-b',
        claim_id: '江苏通州四建',
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
          claim_id: '江苏通州二建',
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
      [1, '江苏通州四建', 7.1],
      [2, '江苏通州二建', 5],
    ])
    expect(data.scoringItems?.[0]).toMatchObject({
      item: '商务标',
      score: 7.1,
      basis: '第二家商务标得 7.1 分。',
    })
  })

  test('buildIssueList derives all seven expert advisory categories from extracted data', () => {
    const result: AuditResult = {
      verdict: 'manual_review',
      extracted_data: {
        disqualification_hits: [
          {
            rule_id: 'DQ-1',
            item: '投标保证金',
            finding: '未按招标文件提交投标保证金。',
            confirmed: true,
            evidence: {
              source: '投标文件 p.3',
              quote: '未见投标保证金凭证',
            },
          },
        ],
        eligibility_checks: [
          {
            rule_id: 'EL-1',
            check: '企业资质',
            status: 'fail',
            basis: '资质等级不满足招标文件要求。',
            evidence: {
              source: '投标文件 p.8',
              quote: '市政公用工程施工总承包三级',
            },
          },
          {
            rule_id: 'EL-2',
            check: '信用中国查询',
            status: 'manual',
            basis: '截图时间不完整，需人工核验。',
          },
        ],
        scoring: [
          {
            item: '企业业绩',
            max: 10,
            score: 8,
            status: 'scored',
            basis: '仅提供 2 个有效业绩。',
            deduction_hits: [
              {
                condition: '每缺少一个同类业绩扣 2 分',
                deducted: 2,
                evidence: {
                  source: '投标文件 p.22',
                  quote: '提供同类业绩 2 项',
                },
              },
            ],
          },
          {
            item: '投标函签字盖章',
            max: 5,
            score: 0,
            status: 'scored',
            basis: '投标函法定代表人未签字。',
          },
          {
            item: '项目负责人证书',
            max: 5,
            score: 0,
            status: 'scored',
            basis: '未提供项目负责人安全 B 证。',
          },
          {
            item: '技术参数响应',
            max: 20,
            score: 15,
            status: 'scored',
            basis: '主要参数存在负偏离。',
          },
          {
            item: '价格分',
            max: 40,
            score: null,
            status: 'manual_review',
            basis: '需全部报价横比后计算。',
          },
        ],
      },
    }

    expect(buildIssueList(result).map((item) => item.category)).toEqual([
      'disqualification_risk',
      'eligibility_mismatch',
      'pending_verification',
      'score_deduction',
      'formality_issue',
      'missing_material',
      'parameter_deviation',
      'pending_verification',
    ])
    expect(buildIssueList(result)[0]).toMatchObject({
      title: '废标风险',
      itemName: '投标保证金',
      quote: '未见投标保证金凭证',
      source: '投标文件 p.3',
    })
  })

  test('buildIssueList keeps uncertain disqualification, manual eligibility, and unreadable wording pending', () => {
    const result: AuditResult = {
      verdict: 'manual_review',
      extracted_data: {
        disqualification_hits: [
          {
            rule_id: 'DQ-uncertain',
            finding: '信用中国截图疑似失信，页面读不清。',
            confirmed: false,
          },
          {
            rule_id: 'DQ-null',
            finding: '投标文件盖章处模糊，待确认。',
            confirmed: null,
          },
          {
            rule_id: 'DQ-old',
            finding: '投标人名称与投标文件不一致。',
          },
          {
            rule_id: 'DQ-unclear-old',
            finding: '截图无法识别，疑似失信。',
          },
        ],
        eligibility_checks: [
          {
            rule_id: 'EL-manual',
            check: '外部信用查询',
            status: 'manual',
            basis: '截图无法识别，需人工核验。',
          },
        ],
        scoring: [
          {
            item: '客观评分',
            max: 10,
            score: null,
            status: 'scored',
            basis: '缺少证据，读不清，不应按 0 分处理。',
          },
        ],
      },
    }

    const issues = buildIssueList(result)
    expect(
      issues
        .filter((item) => item.itemName !== '投标人名称与投标文件不一致。')
        .map((item) => item.category)
    ).toEqual([
      'pending_verification',
      'pending_verification',
      'pending_verification',
      'pending_verification',
      'pending_verification',
    ])
    expect(
      issues.find(
        (item) => item.itemName === '投标人名称与投标文件不一致。'
      )?.category
    ).toBe('disqualification_risk')
  })

  test('buildIssueList tolerates old data and buildTenderReviewData exposes advisory label inputs', () => {
    expect(buildIssueList({ extracted_data: {} })).toEqual([])
    expect(buildIssueList(null)).toEqual([])

    const data = buildTenderReviewData({
      selectedResult: {
        verdict: 'manual_review',
        extracted_data: {
          scoring: [
            {
              item: '价格分',
              max: 40,
              score: null,
              status: 'manual_review',
              basis: '需横比全部投标报价。',
            },
          ],
        },
      },
    })

    expect(data.issueList).toHaveLength(1)
    expect(data.issueList?.[0]).toMatchObject({
      category: 'pending_verification',
      title: '待核验清单',
      itemName: '价格分',
    })
    expect(getAdvisoryLabel(data.issueList)).toBe('较多待确认项')
    expect(getAdvisoryLabel([])).toBe('暂未发现明显问题')
    expect(
      getAdvisoryLabel([
        {
          id: 'issue-risk',
          category: 'disqualification_risk',
          status: 'risk',
          title: '废标风险',
          itemName: '投标保证金',
          basis: '已确认命中否决性条款。',
        },
      ])
    ).toBe('存在废标风险')
  })

  // ── S10 概要分析 checklist：符合性三态派生（复用 S5 同一套源 getter + pending 谓词）──

  const s10Fixture: AuditResult = {
    verdict: 'manual_review',
    extracted_data: {
      eligibility_checks: [
        {
          rule_id: 'EL-pass',
          check: '营业执照',
          status: 'pass',
          basis: '执照在有效期内。',
          evidence: { source: '投标文件 p.2', quote: '统一社会信用代码 91...' },
        },
        {
          rule_id: 'EL-fail',
          check: '企业资质',
          status: 'fail',
          basis: '资质等级不满足招标文件要求。',
        },
        {
          rule_id: 'EL-manual',
          check: '信用中国查询',
          status: 'manual',
          basis: '截图时间不完整，需人工核验。',
        },
      ],
      disqualification_hits: [
        {
          rule_id: 'DQ-confirmed',
          item: '投标保证金',
          finding: '未按招标文件提交投标保证金。',
          confirmed: true,
        },
        {
          rule_id: 'DQ-uncertain',
          item: '信用记录',
          finding: '信用中国截图疑似失信，页面读不清。',
          confirmed: false,
        },
      ],
      scoring: [
        {
          item: '投标函签字盖章',
          max: 5,
          score: 5,
          status: 'scored',
          score_mode: 'pass_fail',
          basis: '投标函法定代表人签字盖章齐全。',
        },
        {
          item: '项目负责人证书',
          max: 5,
          score: 0,
          status: 'scored',
          score_mode: 'pass_fail',
          basis: '未提供项目负责人安全 B 证。',
        },
        {
          item: '关键岗位证书',
          max: 5,
          score: null,
          status: 'manual_review',
          score_mode: 'pass_fail',
          basis: '证书扫描件读不清，待人工核验。',
        },
        {
          item: '必交材料清单',
          max: 3,
          score: 0,
          status: 'rejected',
          basis: '缺少法定代表人授权委托书。',
        },
        {
          item: '技术方案档次',
          max: 20,
          score: 15,
          status: 'scored',
          score_mode: 'banded',
          basis: '技术方案处于良好档。',
        },
        {
          item: '业绩扣分',
          max: 10,
          score: 8,
          status: 'scored',
          score_mode: 'deduction',
          basis: '每缺一个同类业绩扣 2 分。',
        },
        {
          item: '价格分',
          max: 40,
          score: null,
          status: 'manual_review',
          score_mode: 'formula',
          basis: '需横比全部报价后计算。',
        },
      ],
    },
  }

  test('buildOverviewChecklist maps every requirement to met/unmet/pending by group', () => {
    const checklist = buildOverviewChecklist(s10Fixture)
    const byName = (name: string) =>
      checklist.find((item) => item.requirement === name)

    // 资格审查组：pass→met, fail→unmet, manual→pending
    expect(byName('营业执照')).toMatchObject({ group: '资格审查', status: 'met' })
    expect(byName('企业资质')).toMatchObject({ group: '资格审查', status: 'unmet' })
    expect(byName('信用中国查询')).toMatchObject({
      group: '资格审查',
      status: 'pending',
    })

    // 否决条款组：confirmed→unmet, confirmed:false→pending
    expect(byName('投标保证金')).toMatchObject({ group: '否决条款', status: 'unmet' })
    expect(byName('信用记录')).toMatchObject({ group: '否决条款', status: 'pending' })

    // 硬性响应组：pass_fail score≥max→met, score<max→unmet, manual_review→pending, rejected→unmet
    expect(byName('投标函签字盖章')).toMatchObject({
      group: '硬性响应',
      status: 'met',
    })
    expect(byName('项目负责人证书')).toMatchObject({
      group: '硬性响应',
      status: 'unmet',
    })
    expect(byName('关键岗位证书')).toMatchObject({
      group: '硬性响应',
      status: 'pending',
    })
    expect(byName('必交材料清单')).toMatchObject({
      group: '硬性响应',
      status: 'unmet',
    })
  })

  test('buildOverviewChecklist excludes 程度/formula scoring items (范畴错误防护)', () => {
    const names = buildOverviewChecklist(s10Fixture).map((item) => item.requirement)
    expect(names).not.toContain('技术方案档次') // banded 档次
    expect(names).not.toContain('业绩扣分') // deduction 扣减
    expect(names).not.toContain('价格分') // formula 横比价格
  })

  test('buildOverviewChecklist never marks confirmed:false / manual / unreadable as unmet (R2b)', () => {
    const checklist = buildOverviewChecklist(s10Fixture)
    const pendingNames = checklist
      .filter((item) => item.status === 'pending')
      .map((item) => item.requirement)
    expect(pendingNames).toEqual(
      expect.arrayContaining(['信用中国查询', '信用记录', '关键岗位证书'])
    )
    // 三者绝不出现在 unmet 里
    const unmetNames = checklist
      .filter((item) => item.status === 'unmet')
      .map((item) => item.requirement)
    for (const name of ['信用中国查询', '信用记录', '关键岗位证书']) {
      expect(unmetNames).not.toContain(name)
    }
  })

  test('buildOverviewChecklist output carries no numeric score/points/max fields (无分数泄漏)', () => {
    const checklist = buildOverviewChecklist(s10Fixture)
    expect(checklist.length).toBeGreaterThan(0)
    for (const item of checklist) {
      expect(item).not.toHaveProperty('score')
      expect(item).not.toHaveProperty('points')
      expect(item).not.toHaveProperty('max')
      // 每行须有理由；出处 evidence 为数组（可空）
      expect(typeof item.reason).toBe('string')
      expect(Array.isArray(item.evidence)).toBe(true)
    }
  })

  test('buildOverviewChecklist met/unmet consistent with buildIssueList pending set', () => {
    // issueList 里 pending 的项，checklist 对应项不得是 unmet（两视图口径一致）
    const issuePendingNames = new Set(
      buildIssueList(s10Fixture)
        .filter((issue) => issue.status === 'pending')
        .map((issue) => issue.itemName)
    )
    const checklist = buildOverviewChecklist(s10Fixture)
    for (const item of checklist) {
      if (issuePendingNames.has(item.requirement)) {
        expect(item.status).toBe('pending')
      }
    }
  })

  test('buildOverviewChecklist carries evidence source/quote through', () => {
    const checklist = buildOverviewChecklist(s10Fixture)
    const licence = checklist.find((item) => item.requirement === '营业执照')
    expect(licence?.evidence?.[0]).toMatchObject({
      source: '投标文件 p.2',
      quote: '统一社会信用代码 91...',
    })
  })

  test('buildOverviewChecklist tolerates old / empty data', () => {
    expect(buildOverviewChecklist({ extracted_data: {} })).toEqual([])
    expect(buildOverviewChecklist(null)).toEqual([])
    expect(buildOverviewChecklist(undefined)).toEqual([])
    // 仅有可派生项的旧数据不崩、只出可派生行
    const partial = buildOverviewChecklist({
      extracted_data: {
        eligibility_checks: [{ check: '仅资格', status: 'pass' }],
      },
    })
    expect(partial).toHaveLength(1)
    expect(partial[0]).toMatchObject({ group: '资格审查', status: 'met' })
  })

  test('buildTenderReviewData exposes overviewChecklist derived from selectedResult', () => {
    const data = buildTenderReviewData({ selectedResult: s10Fixture })
    expect(Array.isArray(data.overviewChecklist)).toBe(true)
    const checklist = data.overviewChecklist as ChecklistItem[]
    expect(checklist.some((item) => item.requirement === '营业执照')).toBe(true)
  })

  // ── 交叉 review 补漏（CC+Codex 一致 finding）──

  test('buildOverviewChecklist maps unknown / missing eligibility status to pending, not met', () => {
    const checklist = buildOverviewChecklist({
      extracted_data: {
        eligibility_checks: [
          { check: '状态缺失项' }, // 无 status
          { check: '枚举漂移项', status: 'reviewing' }, // 未知枚举
          { check: '明确通过项', status: 'pass' },
        ],
      },
    })
    const statusOf = (name: string) =>
      checklist.find((item) => item.requirement === name)?.status
    expect(statusOf('状态缺失项')).toBe('pending')
    expect(statusOf('枚举漂移项')).toBe('pending')
    expect(statusOf('明确通过项')).toBe('met')
  })

  test('buildOverviewChecklist excludes degree-mode scoring items even when status=rejected', () => {
    const names = buildOverviewChecklist({
      extracted_data: {
        scoring: [
          { item: '档次项被否', max: 10, score: 0, status: 'rejected', score_mode: 'banded' },
          { item: '扣减项被否', max: 10, score: 0, status: 'rejected', score_mode: 'deduction' },
          { item: '加分项被否', max: 10, score: 0, status: 'rejected', score_mode: 'additive' },
          { item: '公式项被否', max: 10, score: null, status: 'rejected', score_mode: 'formula' },
          { item: '必交材料被否', max: 3, score: 0, status: 'rejected' }, // 无 score_mode → 保留
        ],
      },
    }).map((item) => item.requirement)
    expect(names).not.toContain('档次项被否')
    expect(names).not.toContain('扣减项被否')
    expect(names).not.toContain('加分项被否')
    expect(names).not.toContain('公式项被否')
    expect(names).toContain('必交材料被否')
  })

  test('buildOverviewChecklist treats pass_fail with score>0 but missing max as met (缺 max 兜底)', () => {
    const checklist = buildOverviewChecklist({
      extracted_data: {
        scoring: [
          { item: '响应达标无max', score: 5, status: 'scored', score_mode: 'pass_fail' },
          { item: '响应为零无max', score: 0, status: 'scored', score_mode: 'pass_fail' },
        ],
      },
    })
    const statusOf = (name: string) =>
      checklist.find((item) => item.requirement === name)?.status
    expect(statusOf('响应达标无max')).toBe('met')
    expect(statusOf('响应为零无max')).toBe('unmet')
  })

  // ── 交叉 review 第二轮补漏（Codex 对抗性实跑 finding）──

  test('buildOverviewChecklist strips numeric score mentions from reason (P1-c 文本层防泄漏)', () => {
    const checklist = buildOverviewChecklist({
      extracted_data: {
        eligibility_checks: [
          { check: '资格分项', status: 'fail', basis: '资质不符，扣5分。' },
        ],
        scoring: [
          {
            item: '签字项',
            max: 5,
            score: 0,
            status: 'scored',
            score_mode: 'pass_fail',
            basis: '投标函未签字，得0分。',
          },
          {
            item: '材料项',
            max: 3,
            score: 0,
            status: 'rejected',
            basis: '缺授权书（5/10），排名第3。',
          },
          {
            item: '数字在后项',
            max: 5,
            score: 0,
            status: 'rejected',
            basis: '未响应，得分为0，总分80。',
          },
        ],
      },
    })
    expect(checklist.length).toBeGreaterThan(0)
    for (const item of checklist) {
      // 任意"数字±分/得分/总分/分值"两序、排名/名次数字都不得残留
      expect(item.reason).not.toMatch(/\d/u)
    }
    // 定性理由须保留
    expect(
      checklist.find((item) => item.requirement === '签字项')?.reason
    ).toContain('投标函未签字')
  })

  test('buildOverviewChecklist excludes degree item whose score_mode is only in criteria (P1-b)', () => {
    const names = buildOverviewChecklist({
      extracted_data: {
        criteria: { items: [{ item: '技术方案档次', max: 20, score_mode: 'banded' }] },
        scoring: [
          {
            item: '技术方案档次',
            max: 20,
            score: 0,
            status: 'rejected',
            basis: '整单废标残留',
          },
        ],
      },
    }).map((item) => item.requirement)
    expect(names).not.toContain('技术方案档次')
  })

  test('buildOverviewChecklist treats pass_fail status=manual / unreadable basis as pending (P1-a)', () => {
    const checklist = buildOverviewChecklist({
      extracted_data: {
        scoring: [
          {
            item: '现场演示',
            max: 5,
            score: 0,
            status: 'manual',
            score_mode: 'pass_fail',
            basis: '需现场演示记录。',
          },
          {
            item: '扫描证书',
            max: 5,
            score: 0,
            status: 'scored',
            score_mode: 'pass_fail',
            basis: '证书扫描件不可读。',
          },
        ],
      },
    })
    const statusOf = (name: string) =>
      checklist.find((item) => item.requirement === name)?.status
    expect(statusOf('现场演示')).toBe('pending')
    expect(statusOf('扫描证书')).toBe('pending')
  })
})
