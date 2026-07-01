import { useEffect, useMemo, useRef, useState } from 'react'
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import type { AuditResult } from '@/features/audit/types'
import {
  createTenderProject,
  deleteTenderProject,
  evaluateTenderProjectUpload,
  getDocsStatus,
  getTenderDocInfo,
  getTenderCompareOrNull,
  getTenderProject,
  getTenderProjectResult,
  getTenderTask,
  listTenderProjectResults,
  listTenderProjects,
  retryTenderTask,
  triggerTenderCompare,
  uploadBid,
  uploadTenderDoc,
  type TenderProjectCreateRequest,
  type TenderProjectDetailResponse,
} from './api'
import type { ProjectFormData } from './components/create-review-view'
import {
  buildDashboardSummary,
  buildTenderReviewData,
  filterReviewHistory,
  mapTenderProject,
} from './model'
import type {
  HistoryTimeRange,
  ReviewCategory,
  TenderFile,
  TenderReviewScreen,
  TenderReviewMode,
  TenderScenario,
  UploadBidder,
} from './types'

const TENDER_PROJECTS_QUERY_KEY = ['tender-projects'] as const
const SELECTED_PROJECT_KEY = 'tender-selected-project'

// 长任务解耦（第5轮）：进行中评标持久化，可离开/回来恢复，不阻塞 mutation、不超时掉回。
const ACTIVE_EVAL_KEY = 'tender-active-eval'
type ActiveEval = {
  projectId: string
  requestIds: string[]
  hasCompare: boolean
}
function readActiveEval(): ActiveEval | null {
  try {
    const raw = localStorage.getItem(ACTIVE_EVAL_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ActiveEval>
    // shape 校验：脏数据（{}、缺 requestIds）一律丢弃，防 .length 崩溃（codex r5 A+B P1）。
    if (
      !parsed ||
      !Array.isArray(parsed.requestIds) ||
      parsed.requestIds.length === 0
    )
      return null
    return {
      projectId: String(parsed.projectId ?? ''),
      requestIds: parsed.requestIds,
      hasCompare: Boolean(parsed.hasCompare),
    }
  } catch {
    return null
  }
}
function writeActiveEval(value: ActiveEval | null): void {
  try {
    if (value) localStorage.setItem(ACTIVE_EVAL_KEY, JSON.stringify(value))
    else localStorage.removeItem(ACTIVE_EVAL_KEY)
  } catch {
    // localStorage 不可用（隐私模式等）→ 退化为纯内存态，不阻断流程
  }
}

function readSelectedProjectId(): string | null {
  try {
    const projectId = localStorage.getItem(SELECTED_PROJECT_KEY)?.trim() ?? ''
    return projectId && projectId !== '[object Object]' ? projectId : null
  } catch {
    return null
  }
}

function writeSelectedProjectId(projectId: string | null): void {
  try {
    if (projectId) localStorage.setItem(SELECTED_PROJECT_KEY, projectId)
    else localStorage.removeItem(SELECTED_PROJECT_KEY)
  } catch {
    // localStorage 不可用时只保留 React 内存态。
  }
}

/** Default project form — all fields blank so user fills in what they need */
function createDefaultProjectForm(): ProjectFormData {
  return {
    tender_no: '',
    title: '',
    tenderee: '',
    method: '',
    control_price: '',
    funding_type: 'unknown',
  }
}

const DEFAULT_UPLOAD_BIDDER: UploadBidder = {
  id: 1,
  name: '投标单位 1',
  files: [],
}

function toTenderFiles(files: FileList | null): TenderFile[] {
  if (!files?.length) return []
  return Array.from(files).map((file) => ({
    name: file.name,
    size: file.size,
    file,
  }))
}

function hasNativeFile(file: TenderFile): file is TenderFile & { file: File } {
  return file.file instanceof File
}

export function useTenderReviewPage(
  initialScreen: TenderReviewScreen = 'dashboard',
  scenario: TenderScenario = 'expert_assist'
) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [activeEvalSnapshot] = useState<ActiveEval | null>(readActiveEval)
  const resumableActiveEval =
    initialScreen === 'report' ? null : activeEvalSnapshot
  // 恢复：mount 时若 localStorage 有进行中评标 → 直接进 analyzing；报告页不抢占。
  const [screen, setScreen] = useState<TenderReviewScreen>(() =>
    resumableActiveEval ? 'analyzing' : initialScreen
  )
  // S10：单投标人首屏落「概要分析」（概览在前）；多投标人有横比时仍先落「风险对比」。
  const [reviewMode, setReviewMode] = useState<TenderReviewMode>('overview')
  const [category, setCategory] = useState<ReviewCategory>('qual')
  // 恢复：若 localStorage 有进行中评标，selectedProjectId 直接指向该项目（不落到列表[0]，codex r5 P1）。
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    () => resumableActiveEval?.projectId ?? readSelectedProjectId()
  )
  const [selectedBidderId, setSelectedBidderId] = useState('')
  const [activeItemId, setActiveItemId] = useState('result-summary')
  const [query, setQuery] = useState('')
  const [timeRange, setTimeRange] = useState<HistoryTimeRange>('all')
  const [progress, setProgress] = useState(0)
  // 思考流式：按 request_id 存各投标人评标进度，避免多 bidder 并发覆盖（codex r4 P1）。
  const [progressByRid, setProgressByRid] = useState<Record<string, string>>({})
  // 长任务解耦（第5轮）：进行中评标（持久化），可离开/回来恢复、不阻塞、不超时掉回。
  const [activeEval, setActiveEvalState] = useState<ActiveEval | null>(
    () => activeEvalSnapshot
  )
  const setActiveEval = (value: ActiveEval | null) => {
    setActiveEvalState(value)
    writeActiveEval(value)
  }
  const [uploadError, setUploadError] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [destroyNotice, setDestroyNotice] = useState('')
  const [tenderFiles, setTenderFiles] = useState<TenderFile[]>([])
  const [uploadBidders, setUploadBidders] = useState<UploadBidder[]>([
    DEFAULT_UPLOAD_BIDDER,
  ])
  const [nextBidderId, setNextBidderId] = useState(2)
  // P3 两步拆分：uploadProjectId 是"上传即 OCR"后建好的项目 ID（用于 docs-status 轮询）。
  // 置 null 表示尚未上传（初始/取消/新建后）。
  const [uploadProjectId, setUploadProjectId] = useState<string | null>(null)
  // A（上传即 OCR，每区一次多选→自动传→锁定）：招标层一份/每投标一个 bid，故各区上传一次。
  // uploadedBidderIds：已自动上传的投标单位 id（锁定其文件区，防重复 bid）。
  const [uploadedBidderIds, setUploadedBidderIds] = useState<Set<number>>(
    new Set()
  )
  const [uploadingTender, setUploadingTender] = useState(false)
  const [uploadingBidderIds, setUploadingBidderIds] = useState<Set<number>>(
    new Set()
  )
  // R6-R2：记各家预热 bid_id（uploadBid 返回）→ 提交评标时透传，worker 复用预热 OCR 免重 OCR。
  const [prewarmBidIds, setPrewarmBidIds] = useState<Record<number, string>>({})
  // 防招标文件多选时并发重复建项目（createTenderProject 异步，第二次 add 在 resolve 前会重复建）。
  const creatingProjectRef = useRef(false)
  // R7：在途的招标预热上传 promise（resolve 为 project_id）。submitReview 若在它 resolve 前被点，
  // await 它而非另建项目——治"点开始分析时预热还没传完→重复建项目/孤儿"竞态。
  const tenderUploadRef = useRef<Promise<string | null> | null>(null)

  // A①: editable project form state
  const [projectForm, setProjectForm] = useState<ProjectFormData>(
    createDefaultProjectForm
  )
  const isSelfCheck = scenario === 'bidder_self_check'
  const isPostEvalMonitor = scenario === 'post_eval_monitor'
  const projectListScenario = isPostEvalMonitor ? 'expert_assist' : scenario
  const projectListStatus = isPostEvalMonitor ? 'done' : undefined

  function selectProject(projectId: string | null) {
    setSelectedProjectId(projectId)
    writeSelectedProjectId(projectId)
  }

  const projectsQuery = useQuery({
    queryKey: [
      ...TENDER_PROJECTS_QUERY_KEY,
      scenario,
      projectListScenario,
      projectListStatus,
    ],
    queryFn: () =>
      listTenderProjects({
        scenario: projectListScenario,
        status: projectListStatus,
        limit: 100,
      }),
  })

  const selectedProjectIdForQuery =
    selectedProjectId ?? projectsQuery.data?.[0]?.project_id ?? ''
  const shouldLoadSelectedProject = Boolean(
    selectedProjectIdForQuery && (screen === 'analysis' || screen === 'report')
  )

  const projectDetailQuery = useQuery({
    queryKey: ['tender-project', selectedProjectIdForQuery],
    queryFn: () => getTenderProject(selectedProjectIdForQuery),
    enabled: shouldLoadSelectedProject,
  })

  const projectDetailById = useQueries({
    queries: (projectsQuery.data ?? []).map((project) => ({
      queryKey: ['tender-project', project.project_id],
      queryFn: () => getTenderProject(project.project_id),
      enabled: Boolean(projectsQuery.data),
      staleTime: 5000,
    })),
    combine: (results) => {
      const details = new Map<string, TenderProjectDetailResponse>()
      results.forEach((result) => {
        if (result.data) details.set(result.data.project_id, result.data)
      })
      return details
    },
  })

  const resultsQuery = useQuery({
    queryKey: ['tender-project-results', selectedProjectIdForQuery],
    queryFn: () =>
      listTenderProjectResults(selectedProjectIdForQuery, { limit: 200 }),
    enabled: shouldLoadSelectedProject,
  })

  const compareQuery = useQuery({
    queryKey: ['tender-project-compare', selectedProjectIdForQuery],
    queryFn: () => getTenderCompareOrNull(selectedProjectIdForQuery),
    enabled:
      shouldLoadSelectedProject &&
      (projectDetailQuery.data?.bidder_count ?? 0) >= 2,
    refetchInterval: (query) => {
      const compare = query.state.data
      // 遗留③：首次横比由 triggerTenderCompare 异步生成，期间查询返回 null(404)。旧逻辑 null→停轮询
      // → 首次横比永不出现停在空。query 仅在 ≥2 投标且在分析/报告屏时 enabled，故 null 时继续轮询
      // （3s）直到横比生成；已生成且非 stale 才停（离屏由 react-query 自动停，无无界轮询风险）。
      if (compare == null) return 3000
      return compare.stale ? 3000 : false
    },
  })

  // P3 OCR 就绪轮询：上传后 docs-status 每 2.5s 轮询一次，直到招标+至少一家投标均 ready/failed。
  const docsStatusQuery = useQuery({
    queryKey: ['tender-docs-status', uploadProjectId],
    queryFn: () => getDocsStatus(uploadProjectId!),
    enabled: Boolean(uploadProjectId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 2500
      const allDone =
        data.bids.length > 0 &&
        (data.tender_doc?.ocr_status === 'ready' ||
          data.tender_doc?.ocr_status === 'failed')
          ? data.bids.every(
              (bid) => bid.ocr_status === 'ready' || bid.ocr_status === 'failed'
            )
          : false
      return allDone ? false : 2500
    },
  })

  // R1 招标信息（criteria + tender_info）：创建/分析中按当前项目读 tender-doc 层。
  // create 屏只在上传后（uploadProjectId）读；analyzing 屏读正在分析的项目。
  const docInfoProjectId =
    screen === 'create'
      ? uploadProjectId
      : screen === 'analyzing'
        ? (activeEval?.projectId ??
          selectedProjectId ??
          uploadProjectId ??
          null)
        : null
  // criteria_status 非终态时每 2.5s 轮询（OCR 后台抽取进度），ready/failed 即停。
  const tenderDocInfoQuery = useQuery({
    queryKey: ['tender-doc-info', docInfoProjectId],
    queryFn: () => getTenderDocInfo(docInfoProjectId!),
    enabled: Boolean(docInfoProjectId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 2500
      const terminal =
        data.criteria_status === 'ready' || data.criteria_status === 'failed'
      return terminal ? false : 2500
    },
  })

  // OCR 就绪判定：招标层 + 全部投标层均为 ready（failed 不算 ready）。
  const isOcrReady = useMemo(() => {
    if (!uploadProjectId || !docsStatusQuery.data) return false
    const { tender_doc, bids } = docsStatusQuery.data
    if (!tender_doc || tender_doc.ocr_status !== 'ready') return false
    if (bids.length === 0) return false
    return bids.every((bid) => bid.ocr_status === 'ready')
  }, [uploadProjectId, docsStatusQuery.data])

  const selectedResultRequestId = useMemo(() => {
    const results = resultsQuery.data ?? []
    const bySelectedBidder = results.find(
      (result) =>
        result.claim_id === selectedBidderId ||
        result.request_id === selectedBidderId
    )
    return bySelectedBidder?.request_id ?? results[0]?.request_id ?? ''
  }, [resultsQuery.data, selectedBidderId])

  const resultDetailQuery = useQuery({
    queryKey: [
      'tender-project-result',
      selectedProjectIdForQuery,
      selectedResultRequestId,
    ],
    queryFn: () =>
      getTenderProjectResult(
        selectedProjectIdForQuery,
        selectedResultRequestId
      ),
    enabled: Boolean(shouldLoadSelectedProject && selectedResultRequestId),
  })

  const resultDetails = useQueries({
    queries: (resultsQuery.data ?? []).map((result) => ({
      queryKey: [
        'tender-project-result',
        selectedProjectIdForQuery,
        result.request_id,
      ],
      queryFn: () =>
        getTenderProjectResult(selectedProjectIdForQuery, result.request_id),
      enabled: Boolean(shouldLoadSelectedProject && result.request_id),
      staleTime: 5000,
    })),
    combine: (results) =>
      results
        .map((result) => result.data)
        .filter((result): result is AuditResult => Boolean(result)),
  })

  const projects = useMemo(() => {
    const rawProjects = projectsQuery.data ?? []
    const selectedDetail = projectDetailQuery.data
    const compare = compareQuery.data
    const summaries = resultsQuery.data ?? []

    return rawProjects.map((project) =>
      selectedDetail?.project_id === project.project_id
        ? mapTenderProject(selectedDetail, compare, summaries)
        : mapTenderProject(projectDetailById.get(project.project_id) ?? project)
    )
  }, [
    compareQuery.data,
    projectDetailById,
    projectDetailQuery.data,
    projectsQuery.data,
    resultsQuery.data,
  ])

  const summary = useMemo(() => buildDashboardSummary(projects), [projects])
  const history = useMemo(
    () =>
      filterReviewHistory(projects, {
        query,
        timeRange,
        now: new Date().toISOString().slice(0, 10),
      }),
    [projects, query, timeRange]
  )

  const selectedProject =
    projectDetailQuery.data ??
    projectDetailById.get(selectedProjectIdForQuery) ??
    projectsQuery.data?.find(
      (project) => project.project_id === selectedProjectIdForQuery
    ) ??
    null
  const viewData = useMemo(
    () => ({
      ...buildTenderReviewData({
        projects: projectsQuery.data ?? [],
        project: selectedProject,
        resultSummaries: resultsQuery.data ?? [],
        selectedResult: resultDetailQuery.data ?? null,
        resultDetails,
        compare: compareQuery.data ?? null,
      }),
      projects,
    }),
    [
      compareQuery.data,
      projects,
      projectsQuery.data,
      resultDetailQuery.data,
      resultDetails,
      resultsQuery.data,
      selectedProject,
    ]
  )

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const categories = viewData.categories
    if (categories.length === 0) return
    const activeCategory = categories.find((item) => item.key === category)
    const nextCategory = activeCategory ?? categories[0]
    if (!activeCategory) setCategory(nextCategory.key)
    if (!nextCategory.items.some((item) => item.id === activeItemId)) {
      setActiveItemId(nextCategory.items[0]?.id ?? 'result-summary')
    }
  }, [activeItemId, category, viewData.categories])
  /* eslint-enable react-hooks/set-state-in-effect */

  // R7：开始分析**只看本地选了文件**，完全不等任何上传/OCR/预热完成（用户："直接传上去,后台做,
  // 前台不要有提示,不要卡"）。选了招标 + ≥1 家投标文件即可点开始；预热上传/OCR 全在后台，submitReview
  // 内部兜底（await 在途建项目 / 缺预热则现传），用户一路下一步到「开始分析」即可走人。
  const hasFilesSelected =
    tenderFiles.some(hasNativeFile) &&
    uploadBidders.some((bidder) => bidder.files.some(hasNativeFile))
  const canStartReview = hasFilesSelected

  const startReviewMutation = useMutation({
    mutationFn: submitReview,
    onSuccess: ({ projectId, requestIds, hasCompare }) => {
      // 解耦：提交成功即把进行中评标交给 analyzing 独立轮询（不阻塞、不超时掉回）。
      selectProject(projectId)
      setReviewMode(hasCompare ? 'compare' : 'overview')
      setProgressByRid({})
      setProgress(30)
      setActiveEval({ projectId, requestIds, hasCompare })
      void queryClient.invalidateQueries({
        queryKey: TENDER_PROJECTS_QUERY_KEY,
      })
      // 保持 analyzing 界面；全部评标终态后由轮询 effect 跳 analysis
    },
    onError: (error) => {
      setSubmitError(
        error instanceof Error ? error.message : '分析失败，请稍后重试。'
      )
      setProgress(0)
      setScreen('create') // submitReview 只做提交（建项目/上传），失败才回 create 让用户重试
    },
  })

  // A（上传即 OCR）：上传不再走批量按钮 mutation，改由 addTenderFile/addBidderFile 选文件即触发
  // （建项目 + uploadTenderDoc/uploadBid → 后台 OCR）。批量 startUpload/uploadFilesForOcr 已移除。

  // 长任务独立轮询（第5轮）：analyzing 不阻塞在 mutation，由此轮询进行中评标的 task 状态。
  // activeEval 从 localStorage 初始化 → 可离开/回来恢复；不超时掉回。
  const activeEvalQuery = useQuery({
    queryKey: ['tender-active-eval-status', activeEval?.requestIds ?? []],
    enabled: Boolean(activeEval && activeEval.requestIds.length > 0),
    refetchInterval: 2500,
    queryFn: async () =>
      Promise.all(
        (activeEval?.requestIds ?? []).map((rid) =>
          getTenderTask(rid).catch(() => null)
        )
      ),
  })

  // 轮询响应（第5轮）：react-query v5 无 onSuccess，须用 effect 响应 query data；这是合理的
  // "外部数据 → UI 状态"同步，故对本 effect disable set-state-in-effect。
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const statuses = activeEvalQuery.data
    if (!statuses || !activeEval) return
    // 流式：把各家最新 progress 喂展示区
    setProgressByRid((prev) => {
      const next = { ...prev }
      statuses.forEach((status, i) => {
        if (status?.progress_message)
          next[activeEval.requestIds[i]] = status.progress_message
      })
      return next
    })
    // 终态判定：completed/failed 是终态；null（任务 404/已删/不存在）也当终态，否则脏 rid 会永远
    // 停 analyzing 卡死、不清 localStorage（codex r5 A+B P1）。
    const allTerminal = statuses.every(
      (status) =>
        status === null ||
        status.status === 'completed' ||
        status.status === 'failed'
    )
    if (allTerminal) {
      const { projectId, hasCompare } = activeEval
      // 失败可见（P1-4）：有 failed / 任务丢失 → 提示，不被结果列表静默掩盖。
      const failedCount = statuses.filter(
        (s) => !s || s.status === 'failed'
      ).length
      if (failedCount > 0) {
        setSubmitError(
          `${failedCount} 家评标未成功（失败或任务丢失），可在结果页查看或重试。`
        )
      }
      setActiveEval(null)
      setProgress(100)
      if (hasCompare) void triggerTenderCompare(projectId).catch(() => {})
      void queryClient.invalidateQueries({
        queryKey: ['tender-project', projectId],
      })
      void queryClient.invalidateQueries({
        queryKey: ['tender-project-results', projectId],
      })
      if (screen === 'analyzing') {
        setReviewMode(hasCompare ? 'compare' : 'overview')
        setScreen('analysis')
        void navigate({
          to: '/contracts/tender/detail',
          search: { view: 'analysis', scenario },
        })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeEvalQuery.data])
  /* eslint-enable react-hooks/set-state-in-effect */

  // 假死/卡住也能离开（用户诉求）：清进行中态 + 解除 analyzing 锁定 + 回列表。评标后台不管，
  // 用户到列表可手动停止删除（deleteTenderProject 级联清任务）。
  function exitAnalyzing() {
    setActiveEval(null) // 清 localStorage → 解除 screen lazy init 对 analyzing 的锁定
    setProgressByRid({})
    setProgress(0)
    setScreen('dashboard')
  }

  function openAnalysis(
    mode: TenderReviewMode = 'overview',
    projectId = selectedProjectIdForQuery
  ) {
    if (projectId) selectProject(projectId)
    setReviewMode(mode)
    setScreen('analysis')
    void navigate({
      to: '/contracts/tender/detail',
      search: { view: 'analysis', scenario },
    })
  }

  function openHistory() {
    setScreen('history')
    void navigate({ to: '/contracts/tender/history' })
  }

  /**
   * B-C 修复：从列表点开项目时按状态路由——仍在评标中（有未终态投标）→ 重进「分析中」界面并
   * 重建 activeEval 让独立轮询 re-attach（恢复实时进度），而非落到空的分析中心；已全部完成 → 进
   * 分析中心。治"返回列表再回到分析中的界面，回不到真正的分析中的界面"。
   *
   * 取项目详情失败 / 无投标 → 安全回退到 openAnalysis（分析中心）。
   */
  async function resumeOrOpenProject(projectId: string) {
    selectProject(projectId)
    try {
      // staleTime:0 强制新取最新投标状态——否则吃 dashboard useQueries 的 5s 缓存，可能拿到旧的
      // 完成态/空态 bids → inProgress=0 → 误落分析中心（B-C 复发根因）。
      const detail = await queryClient.fetchQuery({
        queryKey: ['tender-project', projectId],
        queryFn: () => getTenderProject(projectId),
        staleTime: 0,
      })
      const bids = detail.bids ?? []
      const inProgress = bids.filter(
        (bid) => bid.status !== 'completed' && bid.status !== 'failed'
      )
      if (inProgress.length > 0) {
        // 重建进行中态 → activeEvalQuery（按 requestIds）re-attach 轮询，analyzing 屏恢复实时进度。
        setProgressByRid({})
        setProgress(30)
        setActiveEval({
          projectId,
          requestIds: inProgress.map((bid) => bid.request_id),
          hasCompare: bids.length >= 2,
        })
        setReviewMode(bids.length >= 2 ? 'compare' : 'overview')
        setScreen('analyzing')
        void navigate({
          to: '/contracts/tender/detail',
          search: { view: 'analysis', scenario },
        })
        return
      }
    } catch {
      // 详情拉取失败 → 回退分析中心（不阻断用户打开项目）
    }
    openAnalysis('overview', projectId)
  }

  function openReport(projectId?: string) {
    const targetProjectId =
      typeof projectId === 'string' && projectId.trim()
        ? projectId
        : selectedProjectIdForQuery
    if (targetProjectId) selectProject(targetProjectId)
    setSelectedBidderId('')
    setScreen('report')
    void navigate({
      to: '/contracts/tender/detail',
      search: { view: 'report', scenario },
    })
  }

  /** A①: update a single field in the project creation form */
  function updateProjectForm(field: keyof ProjectFormData, value: string) {
    setProjectForm((current) => ({ ...current, [field]: value }))
  }

  /** A①/F5: reset the create form to blank (e.g. after the user cancels). */
  function resetProjectForm() {
    setProjectForm(createDefaultProjectForm())
    // P3: 重置时清掉 upload 状态，下次新建重头开始
    setUploadProjectId(null)
    // A：清增量上传态（各区解锁，重头来）
    setTenderFiles([])
    setUploadBidders([DEFAULT_UPLOAD_BIDDER])
    setUploadedBidderIds(new Set())
    setUploadingTender(false)
    setUploadingBidderIds(new Set())
    setPrewarmBidIds({})
    creatingProjectRef.current = false
    tenderUploadRef.current = null
  }

  /**
   * A（上传即 OCR）：选招标文件（一次多选）→ 立即建项目 + 上传 tender-doc + 触发后台 OCR。
   * 招标层一份：已上传(uploadProjectId 非空)或上传中则忽略后续添加（该区锁定，要改→取消重来）。
   */
  async function addTenderFile(files: FileList | null) {
    if (isPostEvalMonitor) return
    const nextFiles = toTenderFiles(files)
    if (nextFiles.length === 0) return
    if (uploadProjectId || uploadingTender || creatingProjectRef.current) return
    const natives = nextFiles.filter(hasNativeFile).map((item) => item.file)
    if (natives.length === 0) return

    setTenderFiles((current) => [...current, ...nextFiles])
    setUploadError(false)
    setSubmitError('')
    creatingProjectRef.current = true
    setUploadingTender(true)
    // 后台预热：建项目 + 上传招标 → 触发后台 OCR。promise 存入 ref 供 submitReview 兜底 await。
    const promise = (async (): Promise<string | null> => {
      try {
        const project = await createTenderProject(
          buildCreateProjectBody(projectForm, natives[0], scenario)
        )
        await uploadTenderDoc(project.project_id, natives) // 触发后台 OCR
        setUploadProjectId(project.project_id)
        return project.project_id
      } catch (error) {
        // 失败回退：清掉刚 staged 的招标文件，让用户重选
        setTenderFiles([])
        setSubmitError(
          error instanceof Error ? error.message : '招标文件上传失败，请重试'
        )
        return null
      } finally {
        setUploadingTender(false)
        creatingProjectRef.current = false
      }
    })()
    tenderUploadRef.current = promise
    await promise
  }

  /**
   * R7-#1：删除招标文件。已上传（建了项目 + 触发后台 OCR）→ 删后端项目级联清（停 OCR + 清 DB + 清盘）
   * 并重置全部上传态，可重新上传正确的招标文件（治"招标文件传错了不能删除"）；未上传则仅去本地暂存项。
   * 招标先传约束下投标依赖招标，故删招标连带重置投标区（重头来）。
   */
  async function removeTenderFile(index: number) {
    if (!uploadProjectId) {
      setTenderFiles((current) =>
        current.filter((_, itemIndex) => itemIndex !== index)
      )
      return
    }
    const pid = uploadProjectId
    // 乐观重置：先清前端态解锁招标区（用户立即可重传），再后台删项目（停 OCR / 级联清）。
    setUploadProjectId(null)
    setTenderFiles([])
    setUploadBidders([DEFAULT_UPLOAD_BIDDER])
    setUploadedBidderIds(new Set())
    setUploadingBidderIds(new Set())
    setPrewarmBidIds({})
    setSubmitError('')
    creatingProjectRef.current = false
    tenderUploadRef.current = null
    try {
      await deleteTenderProject(pid)
    } catch {
      // 删除失败不阻断重传（孤儿项目可在列表手动删）；如实提示。
      setSubmitError(
        '已清空当前上传，但后台项目删除失败，可在项目列表中手动删除。'
      )
    }
    void queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
  }

  function addBidder() {
    if (isSelfCheck || isPostEvalMonitor) return
    const id = nextBidderId
    setUploadBidders((current) => [
      ...current,
      {
        id,
        name: `新增投标单位 ${id}`,
        files: [],
      },
    ])
    setNextBidderId((current) => current + 1)
  }

  function removeBidder(id: number) {
    if (isSelfCheck && uploadBidders.length <= 1) return
    setUploadBidders((current) => current.filter((bidder) => bidder.id !== id))
    // A：删除投标单位时解锁（从已上传集移除；其 bid 在后端由删项目级联清，新建流程不影响）
    setUploadedBidderIds((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }

  function updateBidderName(id: number, name: string) {
    setUploadBidders((current) =>
      current.map((bidder) => (bidder.id === id ? { ...bidder, name } : bidder))
    )
  }

  /**
   * A（上传即 OCR）：选某投标单位的文件（一次多选）→ 立即上传该家 bid + 触发后台 OCR。
   * 招标先传约束：无 uploadProjectId（招标未传）则拒并提示。每家一个 bid：已上传则锁定（要改→删该家重加）。
   */
  async function addBidderFile(id: number, files: FileList | null) {
    if (isPostEvalMonitor) return
    const nextFiles = toTenderFiles(files)
    if (nextFiles.length === 0) return
    if (!uploadProjectId) {
      setSubmitError('请先上传招标文件')
      return
    }
    if (uploadedBidderIds.has(id) || uploadingBidderIds.has(id)) return
    const natives = nextFiles.filter(hasNativeFile).map((item) => item.file)
    if (natives.length === 0) return
    const bidderName = uploadBidders.find((bidder) => bidder.id === id)?.name

    setUploadBidders((current) =>
      current.map((bidder) =>
        bidder.id === id
          ? { ...bidder, files: [...bidder.files, ...nextFiles] }
          : bidder
      )
    )
    setUploadError(false)
    setSubmitError('')
    setUploadingBidderIds((prev) => new Set(prev).add(id))
    try {
      const res = await uploadBid(uploadProjectId, bidderName, natives) // 触发后台 OCR
      setPrewarmBidIds((prev) => ({ ...prev, [id]: res.bid_id })) // R6-R2：记预热 bid_id 供评标复用
      setUploadedBidderIds((prev) => new Set(prev).add(id))
      void queryClient.invalidateQueries({
        queryKey: ['tender-docs-status', uploadProjectId],
      })
    } catch (error) {
      // 失败回退：清掉该家刚 staged 的文件，让用户重选
      setUploadBidders((current) =>
        current.map((bidder) =>
          bidder.id === id ? { ...bidder, files: [] } : bidder
        )
      )
      setSubmitError(
        error instanceof Error
          ? error.message
          : `投标文件上传失败（${bidderName ?? id}），请重试`
      )
    } finally {
      setUploadingBidderIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  function removeBidderFile(id: number, fileIndex: number) {
    setUploadBidders((current) =>
      current.map((bidder) =>
        bidder.id === id
          ? {
              ...bidder,
              files: bidder.files.filter((_, index) => index !== fileIndex),
            }
          : bidder
      )
    )
  }

  /**
   * 第二步：OCR 就绪后用户点击"开始分析"提交评标任务（上传已在选文件时自动完成，A）。
   *
   * 保留 A+B 解耦：submitReview 只做提交（不 await 评标），由 analyzing 独立轮询恢复。
   */
  function startReview() {
    if (isPostEvalMonitor) return
    if (startReviewMutation.isPending) return
    if (!canStartReview) {
      setUploadError(true)
      setSubmitError('')
      return
    }

    setUploadError(false)
    setSubmitError('')
    setProgress(0)
    setProgressByRid({}) // 清上次评标的实时进度
    setScreen('analyzing') // 乐观跳第三步"开始分析"界面；提交在后台跑，失败由 onError 回 create
    startReviewMutation.mutate()
  }

  async function submitReview() {
    const nativeTenderFiles = tenderFiles
      .filter(hasNativeFile)
      .map((item) => item.file)
    const bidders = uploadBidders
      .map((bidder) => ({
        ...bidder,
        nativeFiles: bidder.files
          .filter(hasNativeFile)
          .map((item) => item.file),
      }))
      .filter((bidder) => bidder.nativeFiles.length > 0)

    if (!nativeTenderFiles.length || !bidders.length) {
      throw new Error('请至少上传 1 个招标文件，并为至少一家投标单位上传文件。')
    }

    // R7：复用已建项目（uploadProjectId）→ 若预热上传仍在途，await 其 promise 拿 project_id（不另建，
    // 防孤儿/重复）→ 都没有才现建项目（直接点"开始分析"的 legacy 路径）。
    const inflightProjectId = tenderUploadRef.current
      ? await tenderUploadRef.current
      : null
    const projectId =
      uploadProjectId ??
      inflightProjectId ??
      (
        await createTenderProject(
          buildCreateProjectBody(projectForm, nativeTenderFiles[0], scenario)
        )
      ).project_id

    setProgress(10)

    // partial 容错（codex r5 P1）：逐家提交，单家受理失败不丢已受理的其余家；全失败才 throw 回 create。
    const acceptedTasks = []
    const submitFailures: string[] = []
    for (const [index, bidder] of bidders.entries()) {
      try {
        const accepted = await evaluateTenderProjectUpload(projectId, {
          bidderName: bidder.name,
          tenderFiles: nativeTenderFiles,
          bidderFiles: bidder.nativeFiles,
          bidId: prewarmBidIds[bidder.id], // R6-R2：透传预热 bid_id → worker 复用 OCR 免重跑
        })
        acceptedTasks.push(accepted)
      } catch {
        submitFailures.push(bidder.name)
      }
      setProgress(10 + Math.round(((index + 1) / bidders.length) * 20))
    }
    if (acceptedTasks.length === 0) {
      throw new Error(`全部投标提交失败：${submitFailures.join('、')}`)
    }
    if (submitFailures.length > 0) {
      setSubmitError(
        `部分投标提交失败：${submitFailures.join('、')}（其余已在后台分析）。`
      )
    }

    // 解耦（第5轮）：提交即返回，**不再 await 评标完成**——评标交 analyzing 独立轮询，
    // 用户可离开/回来恢复、不超时掉回。compare 在全部评标终态后由轮询 effect 触发。
    return {
      projectId,
      requestIds: acceptedTasks.map((task) => task.request_id),
      hasCompare: acceptedTasks.length >= 2,
    }
  }

  /**
   * B⑤: Resolve every bid task request_id under the selected projects.
   *
   * The list endpoint (`GET /tender/projects`) does NOT return bids, so we fetch
   * each project's detail (reusing the react-query cache when already loaded) and
   * flatten its `bids[].request_id`. Projects with no bids contribute nothing.
   */
  async function collectBidRequestIds(projectIds: string[]): Promise<string[]> {
    const details = await Promise.all(
      projectIds.map((id) =>
        queryClient.fetchQuery({
          queryKey: ['tender-project', id],
          queryFn: () => getTenderProject(id),
        })
      )
    )
    return details.flatMap((detail) =>
      (detail.bids ?? []).map((bid) => bid.request_id)
    )
  }

  /** B⑤: Batch delete — 删整个招标项目（后端级联删投标任务/结论/横比），空项目也能删。 */
  async function batchDeleteProjects(projectIds: string[]) {
    if (isPostEvalMonitor) return
    if (projectIds.length === 0) return
    const results = await Promise.allSettled(
      projectIds.map((id) => deleteTenderProject(id))
    )
    await queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
    reportBatchFailures(results, projectIds.length, '删除')
  }

  /** B⑤: Batch retry — re-run every bid task under each selected project. */
  async function batchRetryProjects(projectIds: string[]) {
    if (isPostEvalMonitor) return
    const requestIds = await collectBidRequestIds(projectIds)
    if (requestIds.length === 0) return
    const results = await Promise.allSettled(
      requestIds.map((id) => retryTenderTask(id))
    )
    await queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
    reportBatchFailures(results, requestIds.length, '重新审核')
  }

  /**
   * B⑥: Append a new bidder to an existing project.
   * Calls POST /tender/projects/{id}/evaluate with mode=upload.
   */
  async function appendBidder(
    projectId: string,
    bidderName: string | undefined,
    tenderFiles: File[],
    bidderFiles: File[]
  ) {
    if (isPostEvalMonitor) return
    await evaluateTenderProjectUpload(projectId, {
      bidderName,
      tenderFiles,
      bidderFiles,
    })
    await queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
    await queryClient.invalidateQueries({
      queryKey: ['tender-project', projectId],
    })
  }

  async function confirmSelfCheckReportDownloaded() {
    if (!isSelfCheck || !selectedProjectIdForQuery) return
    window.print()
    const confirmed = window.confirm('报告已下载后，将销毁服务器上的项目文件。确认继续？')
    if (!confirmed) return
    try {
      await deleteTenderProject(selectedProjectIdForQuery)
      setDestroyNotice('文件已从服务器销毁')
      setActiveEval(null)
      selectProject(null)
      await queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
      setScreen('dashboard')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '文件销毁失败，请稍后重试。')
    }
  }

  // 思考流式：多投标人并行时按序号分段拼接各家进度，单家直接显示（codex r4 P1：防并发覆盖）。
  // 按提交顺序（activeEval.requestIds）排列各家进度，标签不错位（codex r5 P2）。
  const orderedRids = activeEval?.requestIds ?? Object.keys(progressByRid)
  const progressEntries = orderedRids
    .map((rid) => progressByRid[rid])
    .filter(Boolean)
  const progressText =
    progressEntries.length <= 1
      ? (progressEntries[0] ?? '')
      : progressEntries
          .map((text, i) => `── 投标 ${i + 1} ──\n${text}`)
          .join('\n\n')

  return {
    screen,
    setScreen,
    reviewMode,
    setReviewMode,
    category,
    setCategory,
    selectedBidderId,
    setSelectedBidderId,
    activeItemId,
    setActiveItemId,
    query,
    timeRange,
    setQuery,
    setTimeRange,
    progress,
    progressText,
    isAnalyzing: startReviewMutation.isPending,
    exitAnalyzing,
    // A 上传即 OCR：增量上传态（招标/各投标各上传一次后锁定）
    isUploading: uploadingTender || uploadingBidderIds.size > 0,
    uploadingTender,
    uploadedBidderIds,
    uploadingBidderIds,
    uploadProjectId,
    docsStatus: docsStatusQuery.data ?? null,
    tenderDocInfo: tenderDocInfoQuery.data ?? null,
    isOcrReady,
    hasFilesSelected,
    uploadError,
    submitError,
    projectForm,
    tenderFiles,
    uploadBidders,
    canStartReview,
    startReview,
    updateProjectForm,
    resetProjectForm,
    addTenderFile,
    removeTenderFile,
    addBidder,
    removeBidder,
    updateBidderName,
    addBidderFile,
    removeBidderFile,
    openAnalysis,
    openHistory,
    resumeOrOpenProject,
    openReport,
    batchDeleteProjects,
    batchRetryProjects,
    appendBidder,
    confirmSelfCheckReportDownloaded,
    destroyNotice,
    scenario,
    isSelfCheck,
    isPostEvalMonitor,
    viewModel: {
      summary,
      history,
      data: viewData,
      isLoading: projectsQuery.isLoading,
      error:
        projectsQuery.error instanceof Error
          ? projectsQuery.error.message
          : projectDetailQuery.error instanceof Error
            ? projectDetailQuery.error.message
            : null,
    },
  }
}

/**
 * A①: Build the project creation body from the user-supplied form.
 * All 6 fields are passed through; a fallback title is derived from the
 * first tender file name only when the user left title blank.
 */
function buildCreateProjectBody(
  form: ProjectFormData,
  firstTenderFile: File,
  scenario: TenderScenario = 'expert_assist'
): TenderProjectCreateRequest {
  const title =
    form.title?.trim() ||
    stripExtension(firstTenderFile.name) ||
    '新建招投标项目'
  const tender_no =
    form.tender_no?.trim() || deriveTenderNo(firstTenderFile.name)
  return {
    scenario,
    tender_no,
    title,
    tenderee: form.tenderee?.trim() || undefined,
    method: form.method?.trim() || undefined,
    control_price: form.control_price?.trim() || undefined,
    funding_type: form.funding_type || 'unknown',
  }
}

function deriveTenderNo(fileName: string) {
  const normalized = stripExtension(fileName)
  const matched = normalized.match(/[A-Za-z0-9][A-Za-z0-9_-]{4,}/u)
  return matched?.[0] ?? `TR-${Date.now()}`
}

function stripExtension(fileName: string) {
  return fileName.replace(/\.[^.]+$/u, '').trim()
}

/** B⑤: Throw a single user-facing error if any batched task operation failed. */
function reportBatchFailures(
  results: PromiseSettledResult<unknown>[],
  total: number,
  action: string
): void {
  const failed = results.filter((result) => result.status === 'rejected').length
  if (failed > 0) {
    throw new Error(`${failed}/${total} 个任务${action}失败，请稍后重试。`)
  }
}
