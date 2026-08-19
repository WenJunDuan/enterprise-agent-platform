/**
 * 评标提交 / 任务失败文案透传（2026-08-19 收单等就绪语义的前端侧）。
 *
 * 实测缺陷（2026-08-18 用户实操）：后端 409 的 detail 是一段自带可执行动作的中文
 * （「招标文件详情页的解析状态转为「已就绪」后重新提交即可」），前端却渲染成
 * 「全部投标提交失败：投标单位 1」——用户看不到发生了什么，也不知道该做什么。
 * 下面的断言钉住"后端说什么就显示什么"。
 */
import { expect, test } from 'bun:test'
import { describeSubmitFailures, describeTaskFailures } from './submit-feedback'

const CRITERIA_REUPLOAD_DETAIL =
  '本项目的评分标准解析未成功，暂时无法评标：请重新上传招标文件触发重新解析，' +
  '或改用可检索的电子版招标文件（扫描件缺文字层时解析常失败）。（原因：评分标准的 items 评分项为空（items_empty））'

const CRITERIA_TIMEOUT_DETAIL =
  '本项目的评分标准仍在解析中：本次评标已自动等待 1800 秒仍未就绪，未开始判分。' +
  '招标文件详情页的解析状态转为「已就绪」后重新提交即可。'

test('全部提交失败时透传后端原文，而不是只报投标单位名', () => {
  const message = describeSubmitFailures(
    [{ bidderName: '投标单位 1', reason: CRITERIA_REUPLOAD_DETAIL }],
    0
  )

  expect(message).toContain(CRITERIA_REUPLOAD_DETAIL)
  expect(message).toContain('投标单位 1')
})

test('同一后端原因的多家投标合并成一条，不重复刷屏', () => {
  const message = describeSubmitFailures(
    [
      { bidderName: '甲公司', reason: CRITERIA_REUPLOAD_DETAIL },
      { bidderName: '乙公司', reason: CRITERIA_REUPLOAD_DETAIL },
    ],
    0
  )

  expect(message).toContain('甲公司')
  expect(message).toContain('乙公司')
  // 原文只出现一次：三家四家时逐条重复同一段长文案会把提示挤爆。
  expect(message.split(CRITERIA_REUPLOAD_DETAIL).length - 1).toBe(1)
})

test('原因不同的多家各自成条', () => {
  const message = describeSubmitFailures(
    [
      { bidderName: '甲公司', reason: CRITERIA_REUPLOAD_DETAIL },
      { bidderName: '乙公司', reason: '评标队列已满，请稍后重试' },
    ],
    0
  )

  expect(message).toContain(CRITERIA_REUPLOAD_DETAIL)
  expect(message).toContain('评标队列已满，请稍后重试')
})

test('部分受理时说明已受理家数，同时保留失败原文', () => {
  const message = describeSubmitFailures(
    [{ bidderName: '丙公司', reason: '评标队列已满，请稍后重试' }],
    2
  )

  expect(message).toContain('丙公司')
  expect(message).toContain('评标队列已满，请稍后重试')
  expect(message).toContain('2')
  expect(message).toContain('后台')
})

test('后端没给原因时回落泛化文案，不留空白', () => {
  const message = describeSubmitFailures(
    [{ bidderName: '丁公司', reason: '   ' }],
    0
  )

  expect(message).toContain('丁公司')
  expect(message.trim().endsWith('：')).toBe(false)
  expect(message).toContain('重试')
})

test('投标单位没填名字时用占位名，不出现空档', () => {
  const message = describeSubmitFailures(
    [{ bidderName: '', reason: '内部错误' }],
    0
  )

  expect(message).not.toContain('：：')
  expect(message).toContain('内部错误')
  expect(message).toContain('未命名投标单位')
})

test('failed 任务展示后端 error_detail 原文（评分标准未就绪一类）', () => {
  const notice = describeTaskFailures([
    { status: 'completed', error_detail: null },
    { status: 'failed', error_detail: CRITERIA_TIMEOUT_DETAIL },
  ])

  expect(notice).toContain(CRITERIA_TIMEOUT_DETAIL)
})

test('多家同因失败去重后仍给出失败家数', () => {
  const notice = describeTaskFailures([
    { status: 'failed', error_detail: CRITERIA_TIMEOUT_DETAIL },
    { status: 'failed', error_detail: CRITERIA_TIMEOUT_DETAIL },
  ])

  expect(notice).toContain('2')
  expect(notice?.split(CRITERIA_TIMEOUT_DETAIL).length ?? 0).toBe(2)
})

test('failed 但后端没给原因时给可执行回落，指向既有重试入口', () => {
  const notice = describeTaskFailures([
    { status: 'failed', error_detail: null },
  ])

  expect(notice).not.toBeNull()
  expect(notice).toContain('重新审核')
})

test('任务丢失（轮询取不到）单独计数，不混进失败原因', () => {
  const notice = describeTaskFailures([
    null,
    { status: 'failed', error_detail: CRITERIA_TIMEOUT_DETAIL },
  ])

  expect(notice).toContain(CRITERIA_TIMEOUT_DETAIL)
  expect(notice).toContain('丢失')
})

test('全部完成时不造提示（假告警会让真告警被无视）', () => {
  expect(
    describeTaskFailures([
      { status: 'completed', error_detail: null },
      { status: 'completed', error_detail: null },
    ])
  ).toBeNull()
  expect(describeTaskFailures([])).toBeNull()
})
