/**
 * 评标提交 / 任务失败的用户文案（2026-08-19「收单等就绪」语义的前端侧）。
 *
 * 后端在提交口（409 `detail`）与任务失败侧（`error_detail`）给出的已经是**面向用户的中文**，
 * 且自带可执行动作（如「招标文件详情页的解析状态转为「已就绪」后重新提交即可」）。前端唯一
 * 该做的是把它端上来，而不是另起一句泛化文案盖住它——2026-08-18 用户实操实测到的正是后者：
 * 后端说了整段原因，界面只显示「全部投标提交失败：投标单位 1」。
 *
 * 文案组装单独成模块（而不是内联在 `use-tender-review-page`）是为了让"说什么"可以单测钉住：
 * 页面 hook 依赖 react-query / 上传 ref / 屏幕状态，在单测里无法只为一句文案把它整个搭起来。
 */

/** 单家投标的提交失败记录。 */
export type BidderSubmitFailure = {
  /** 投标单位显示名；用户可能没填，此时为空串。 */
  bidderName: string
  /** 后端 `detail` / `error.message` 原文（由 `handleResponse` 抛出）；拿不到时为空串。 */
  reason: string
}

/** 轮询到的评标任务终态片段；`null` 表示任务查不到（已删 / 脏 request_id）。 */
export type TenderTaskFailureInput = {
  status: string
  error_detail?: string | null
} | null

const UNNAMED_BIDDER = '未命名投标单位'

/** 后端连原因都没给时的兜底：不留空白，且指向用户能做的下一步。 */
const SUBMIT_FALLBACK_REASON = '提交未被受理，请稍后重试。'

/** 任务 failed 但 error_detail 为空时的兜底：指向列表页既有的「重新审核」入口。 */
const TASK_FALLBACK_REASON =
  '后端未返回失败原因，可在项目列表选中该项目后「重新审核」。'

/** 按原因归并投标单位：多家撞同一个 409（如评分标准解析失败）时只说一遍原因。 */
function groupByReason(
  failures: readonly BidderSubmitFailure[]
): Array<{ reason: string; names: string[] }> {
  const grouped: Array<{ reason: string; names: string[] }> = []
  for (const failure of failures) {
    const reason = failure.reason.trim() || SUBMIT_FALLBACK_REASON
    const name = failure.bidderName.trim() || UNNAMED_BIDDER
    const existing = grouped.find((group) => group.reason === reason)
    if (existing) existing.names.push(name)
    else grouped.push({ reason, names: [name] })
  }
  return grouped
}

/**
 * 组装投标提交失败的提示语。
 *
 * @param failures - 逐家提交失败的记录（调用方保证非空；空数组由调用方短路，不在这里造分支）。
 * @param acceptedCount - 已被受理的家数；> 0 时说明其余家仍在后台跑，别让用户以为整单废了。
 * @returns 面向用户的中文提示，含后端原文。
 */
export function describeSubmitFailures(
  failures: readonly BidderSubmitFailure[],
  acceptedCount: number
): string {
  const lines = groupByReason(failures).map(
    (group) => `${group.names.join('、')}：${group.reason}`
  )
  const head =
    acceptedCount > 0
      ? `部分投标提交失败（其余 ${acceptedCount} 家已在后台分析）`
      : '投标提交失败'
  return `${head}——${lines.join('；')}`
}

/**
 * 组装评标任务终态的失败提示语。
 *
 * `failed` 任务的 `error_detail` 是后端写的可执行说明（含「评分标准未就绪 / 解析失败」一类），
 * 原文透出；同因多家去重。查不到的任务（轮询返回 null）单列，因为它不是评标失败而是任务没了。
 *
 * @param statuses - 本次评标各任务的最新状态（与 `activeEval.requestIds` 同序）。
 * @returns 提示语；没有失败也没有丢失时返回 `null`（不造假告警）。
 */
export function describeTaskFailures(
  statuses: readonly TenderTaskFailureInput[]
): string | null {
  const failed = statuses.filter(
    (status): status is NonNullable<TenderTaskFailureInput> =>
      status?.status === 'failed'
  )
  const lostCount = statuses.filter((status) => status === null).length
  if (failed.length === 0 && lostCount === 0) return null

  const parts: string[] = []
  if (failed.length > 0) {
    const reasons = [
      ...new Set(
        failed.map((task) => task.error_detail?.trim() || TASK_FALLBACK_REASON)
      ),
    ]
    parts.push(`${failed.length} 家评标未成功：${reasons.join('；')}`)
  }
  if (lostCount > 0) {
    parts.push(`另有 ${lostCount} 个评标任务已丢失或被删除。`)
  }
  return parts.join(' ')
}
