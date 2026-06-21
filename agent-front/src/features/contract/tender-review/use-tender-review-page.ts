import { useEffect, useMemo, useState } from 'react'
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
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
  UploadBidder,
} from './types'
import type { ProjectFormData } from './components/create-review-view'

const TENDER_PROJECTS_QUERY_KEY = ['tender-projects'] as const

// 长任务解耦（第5轮）：进行中评标持久化，可离开/回来恢复，不阻塞 mutation、不超时掉回。
const ACTIVE_EVAL_KEY = 'tender-active-eval'
type ActiveEval = { projectId: string; requestIds: string[]; hasCompare: boolean }
function readActiveEval(): ActiveEval | null {
  try {
    const raw = localStorage.getItem(ACTIVE_EVAL_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ActiveEval>
    // shape 校验：脏数据（{}、缺 requestIds）一律丢弃，防 .length 崩溃（codex r5 A+B P1）。
    if (!parsed || !Array.isArray(parsed.requestIds) || parsed.requestIds.length === 0) return null
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
  initialScreen: TenderReviewScreen = 'dashboard'
) {
  const queryClient = useQueryClient()
  // 恢复：mount 时若 localStorage 有进行中评标 → 直接进 analyzing 继续流式（lazy init 免 effect）。
  const [screen, setScreen] = useState<TenderReviewScreen>(() =>
    readActiveEval() ? 'analyzing' : initialScreen
  )
  const [reviewMode, setReviewMode] = useState<TenderReviewMode>('detail')
  const [category, setCategory] = useState<ReviewCategory>('qual')
  // 恢复：若 localStorage 有进行中评标，selectedProjectId 直接指向该项目（不落到列表[0]，codex r5 P1）。
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    () => readActiveEval()?.projectId ?? null
  )
  const [selectedBidderId, setSelectedBidderId] = useState('')
  const [activeItemId, setActiveItemId] = useState('result-summary')
  const [query, setQuery] = useState('')
  const [timeRange, setTimeRange] = useState<HistoryTimeRange>('all')
  const [progress, setProgress] = useState(0)
  // 思考流式：按 request_id 存各投标人评标进度，避免多 bidder 并发覆盖（codex r4 P1）。
  const [progressByRid, setProgressByRid] = useState<Record<string, string>>({})
  // 长任务解耦（第5轮）：进行中评标（持久化），可离开/回来恢复、不阻塞、不超时掉回。
  const [activeEval, setActiveEvalState] = useState<ActiveEval | null>(readActiveEval)
  const setActiveEval = (value: ActiveEval | null) => {
    setActiveEvalState(value)
    writeActiveEval(value)
  }
  const [uploadError, setUploadError] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [tenderFiles, setTenderFiles] = useState<TenderFile[]>([])
  const [uploadBidders, setUploadBidders] = useState<UploadBidder[]>([
    DEFAULT_UPLOAD_BIDDER,
  ])
  const [nextBidderId, setNextBidderId] = useState(2)
  // P3 两步拆分：uploadProjectId 是"上传即 OCR"后建好的项目 ID（用于 docs-status 轮询）。
  // 置 null 表示尚未上传（初始/取消/新建后）。
  const [uploadProjectId, setUploadProjectId] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  // A①: editable project form state
  const [projectForm, setProjectForm] = useState<ProjectFormData>(
    createDefaultProjectForm
  )

  const projectsQuery = useQuery({
    queryKey: TENDER_PROJECTS_QUERY_KEY,
    queryFn: () => listTenderProjects({ limit: 100 }),
  })

  const selectedProjectIdForQuery =
    selectedProjectId ?? projectsQuery.data?.[0]?.project_id ?? ''
  const shouldLoadSelectedProject = Boolean(
    selectedProjectIdForQuery &&
      (screen === 'analysis' || screen === 'report')
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
    queryFn: () => listTenderProjectResults(selectedProjectIdForQuery, { limit: 200 }),
    enabled: shouldLoadSelectedProject,
  })

  const compareQuery = useQuery({
    queryKey: ['tender-project-compare', selectedProjectIdForQuery],
    queryFn: () => getTenderCompareOrNull(selectedProjectIdForQuery),
    enabled:
      shouldLoadSelectedProject && (projectDetailQuery.data?.bidder_count ?? 0) >= 2,
    refetchInterval: (query) => {
      const compare = query.state.data
      if (compare == null) return false
      return compare.stale ? 3000 : false
    },
  })

  // P3 OCR 就绪轮询：上传后 docs-status 每 2.5s 轮询一次，直到招标+所有投标均 ready/failed。
  const docsStatusQuery = useQuery({
    queryKey: ['tender-docs-status', uploadProjectId],
    queryFn: () => getDocsStatus(uploadProjectId!),
    enabled: Boolean(uploadProjectId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 2500
      const allDone =
        data.tender_doc?.ocr_status === 'ready' ||
        data.tender_doc?.ocr_status === 'failed'
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
        ? (activeEval?.projectId ?? selectedProjectId ?? uploadProjectId ?? null)
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
      getTenderProjectResult(selectedProjectIdForQuery, selectedResultRequestId),
    enabled: Boolean(shouldLoadSelectedProject && selectedResultRequestId),
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
    projectsQuery.data?.find((project) => project.project_id === selectedProjectIdForQuery) ??
    null
  const viewData = useMemo(
    () => ({
      ...buildTenderReviewData({
        projects: projectsQuery.data ?? [],
        project: selectedProject,
        resultSummaries: resultsQuery.data ?? [],
        selectedResult: resultDetailQuery.data ?? null,
        compare: compareQuery.data ?? null,
      }),
      projects,
    }),
    [
      compareQuery.data,
      projects,
      projectsQuery.data,
      resultDetailQuery.data,
      resultsQuery.data,
      selectedProject,
    ]
  )

  // P3 两步拆分：文件已上传且 OCR 就绪时才允许"开始分析"（上传阶段仅判断文件存在）。
  const hasFilesSelected =
    tenderFiles.some(hasNativeFile) &&
    uploadBidders.some((bidder) => bidder.files.some(hasNativeFile))
  // 已完成上传且 OCR ready → 允许提交评标；尚未上传 → 用文件选取判断（显示上传按钮语义）。
  const canStartReview = uploadProjectId ? isOcrReady : hasFilesSelected

  const startReviewMutation = useMutation({
    mutationFn: submitReview,
    onSuccess: ({ projectId, requestIds, hasCompare }) => {
      // 解耦：提交成功即把进行中评标交给 analyzing 独立轮询（不阻塞、不超时掉回）。
      setSelectedProjectId(projectId)
      setReviewMode(hasCompare ? 'compare' : 'detail')
      setProgressByRid({})
      setProgress(30)
      setActiveEval({ projectId, requestIds, hasCompare })
      void queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
      // 保持 analyzing 界面；全部评标终态后由轮询 effect 跳 analysis
    },
    onError: (error) => {
      setSubmitError(error instanceof Error ? error.message : '分析失败，请稍后重试。')
      setProgress(0)
      setScreen('create') // submitReview 只做提交（建项目/上传），失败才回 create 让用户重试
    },
  })

  // P3 上传阶段 mutation：建项目 + uploadTenderDoc + uploadBid → 触发后台 OCR。
  const uploadFilesMutation = useMutation({
    mutationFn: uploadFilesForOcr,
    onSuccess: (projectId) => {
      setUploadProjectId(projectId)
      setIsUploading(false)
      setSubmitError('')
    },
    onError: (error) => {
      setIsUploading(false)
      setSubmitError(error instanceof Error ? error.message : '文件上传失败，请稍后重试。')
    },
  })

  // 长任务独立轮询（第5轮）：analyzing 不阻塞在 mutation，由此轮询进行中评标的 task 状态。
  // activeEval 从 localStorage 初始化 → 可离开/回来恢复；不超时掉回。
  const activeEvalQuery = useQuery({
    queryKey: ['tender-active-eval-status', activeEval?.requestIds ?? []],
    enabled: Boolean(activeEval && activeEval.requestIds.length > 0),
    refetchInterval: 2500,
    queryFn: async () =>
      Promise.all(
        (activeEval?.requestIds ?? []).map((rid) => getTenderTask(rid).catch(() => null))
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
        if (status?.progress_message) next[activeEval.requestIds[i]] = status.progress_message
      })
      return next
    })
    // 终态判定：completed/failed 是终态；null（任务 404/已删/不存在）也当终态，否则脏 rid 会永远
    // 停 analyzing 卡死、不清 localStorage（codex r5 A+B P1）。
    const allTerminal = statuses.every(
      (status) => status === null || status.status === 'completed' || status.status === 'failed'
    )
    if (allTerminal) {
      const { projectId, hasCompare } = activeEval
      // 失败可见（P1-4）：有 failed / 任务丢失 → 提示，不被结果列表静默掩盖。
      const failedCount = statuses.filter((s) => !s || s.status === 'failed').length
      if (failedCount > 0) {
        setSubmitError(`${failedCount} 家评标未成功（失败或任务丢失），可在结果页查看或重试。`)
      }
      setActiveEval(null)
      setProgress(100)
      if (hasCompare) void triggerTenderCompare(projectId).catch(() => {})
      setReviewMode(hasCompare ? 'compare' : 'detail')
      setScreen('analysis')
      void queryClient.invalidateQueries({ queryKey: ['tender-project', projectId] })
      void queryClient.invalidateQueries({ queryKey: ['tender-project-results', projectId] })
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
    mode: TenderReviewMode = 'detail',
    projectId = selectedProjectIdForQuery
  ) {
    if (projectId) setSelectedProjectId(projectId)
    setReviewMode(mode)
    setScreen('analysis')
  }

  function openReport(projectId = selectedProjectIdForQuery) {
    if (projectId) setSelectedProjectId(projectId)
    setScreen('report')
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
    setIsUploading(false)
  }

  function addTenderFile(files: FileList | null) {
    const nextFiles = toTenderFiles(files)
    if (nextFiles.length === 0) return

    setTenderFiles((current) => [
      ...current,
      ...nextFiles,
    ])
    setUploadError(false)
    setSubmitError('')
  }

  function removeTenderFile(index: number) {
    setTenderFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))
  }

  function addBidder() {
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
    setUploadBidders((current) => current.filter((bidder) => bidder.id !== id))
  }

  function updateBidderName(id: number, name: string) {
    setUploadBidders((current) =>
      current.map((bidder) => (bidder.id === id ? { ...bidder, name } : bidder))
    )
  }

  function addBidderFile(id: number, files: FileList | null) {
    const nextFiles = toTenderFiles(files)
    if (nextFiles.length === 0) return

    setUploadBidders((current) =>
      current.map((bidder) =>
        bidder.id === id
          ? {
              ...bidder,
              files: [...bidder.files, ...nextFiles],
            }
          : bidder
      )
    )
    setUploadError(false)
    setSubmitError('')
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
   * P3 两步拆分 — 第一步：选完文件后上传并触发后台 OCR。
   *
   * 上传成功后 uploadProjectId 置位，前端开始轮询 docs-status；
   * "开始分析"按钮在 isOcrReady 前一直禁用。
   */
  function startUpload() {
    if (uploadFilesMutation.isPending || isUploading) return
    if (!hasFilesSelected) {
      setUploadError(true)
      setSubmitError('')
      return
    }
    setUploadError(false)
    setSubmitError('')
    setIsUploading(true)
    uploadFilesMutation.mutate()
  }

  /**
   * P3 两步拆分 — 第二步：OCR 就绪后用户点击"开始分析"提交评标任务。
   *
   * 保留 A+B 解耦：submitReview 只做提交（不 await 评标），由 analyzing 独立轮询恢复。
   */
  function startReview() {
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

  /**
   * P3 第一步：建项目 + uploadTenderDoc + uploadBid per bidder（上传即 OCR）。
   *
   * 返回 projectId，供 docsStatusQuery 轮询 OCR 进度。
   */
  async function uploadFilesForOcr(): Promise<string> {
    const nativeTenderFiles = tenderFiles.filter(hasNativeFile).map((item) => item.file)
    const bidders = uploadBidders
      .map((bidder) => ({
        ...bidder,
        nativeFiles: bidder.files.filter(hasNativeFile).map((item) => item.file),
      }))
      .filter((bidder) => bidder.nativeFiles.length > 0)

    if (!nativeTenderFiles.length || !bidders.length) {
      throw new Error('请至少上传 1 个招标文件，并为至少一家投标单位上传文件。')
    }

    // 建项目（幂等 get-or-create）
    const project = await createTenderProject(
      buildCreateProjectBody(projectForm, nativeTenderFiles[0])
    )
    const projectId = project.project_id

    // 上传招标文件 → 后台 OCR
    await uploadTenderDoc(projectId, nativeTenderFiles)

    // 逐家上传投标文件 → 后台 OCR（部分失败不整体中断）
    const uploadFailures: string[] = []
    for (const bidder of bidders) {
      try {
        await uploadBid(projectId, bidder.name, bidder.nativeFiles)
      } catch {
        uploadFailures.push(bidder.name)
      }
    }
    if (uploadFailures.length === bidders.length) {
      throw new Error(`全部投标文件上传失败：${uploadFailures.join('、')}`)
    }
    if (uploadFailures.length > 0) {
      setSubmitError(
        `部分投标文件上传失败：${uploadFailures.join('、')}（其余正在 OCR 识别中）。`
      )
    }

    return projectId
  }

  async function submitReview() {
    const nativeTenderFiles = tenderFiles.filter(hasNativeFile).map((item) => item.file)
    const bidders = uploadBidders
      .map((bidder) => ({
        ...bidder,
        nativeFiles: bidder.files.filter(hasNativeFile).map((item) => item.file),
      }))
      .filter((bidder) => bidder.nativeFiles.length > 0)

    if (!nativeTenderFiles.length || !bidders.length) {
      throw new Error('请至少上传 1 个招标文件，并为至少一家投标单位上传文件。')
    }

    // P3 两步拆分：若已有 uploadProjectId（上传阶段完成，OCR ready），复用它；
    // 否则（直接点"开始分析"旧路径/legacy）继续建项目。
    const projectId =
      uploadProjectId ??
      (await createTenderProject(buildCreateProjectBody(projectForm, nativeTenderFiles[0]))).project_id

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
      setSubmitError(`部分投标提交失败：${submitFailures.join('、')}（其余已在后台分析）。`)
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
    return details.flatMap((detail) => (detail.bids ?? []).map((bid) => bid.request_id))
  }

  /** B⑤: Batch delete — 删整个招标项目（后端级联删投标任务/结论/横比），空项目也能删。 */
  async function batchDeleteProjects(projectIds: string[]) {
    if (projectIds.length === 0) return
    const results = await Promise.allSettled(
      projectIds.map((id) => deleteTenderProject(id))
    )
    await queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
    reportBatchFailures(results, projectIds.length, '删除')
  }

  /** B⑤: Batch retry — re-run every bid task under each selected project. */
  async function batchRetryProjects(projectIds: string[]) {
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
    await evaluateTenderProjectUpload(projectId, {
      bidderName,
      tenderFiles,
      bidderFiles,
    })
    await queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
    await queryClient.invalidateQueries({ queryKey: ['tender-project', projectId] })
  }

  // 思考流式：多投标人并行时按序号分段拼接各家进度，单家直接显示（codex r4 P1：防并发覆盖）。
  // 按提交顺序（activeEval.requestIds）排列各家进度，标签不错位（codex r5 P2）。
  const orderedRids = activeEval?.requestIds ?? Object.keys(progressByRid)
  const progressEntries = orderedRids.map((rid) => progressByRid[rid]).filter(Boolean)
  const progressText =
    progressEntries.length <= 1
      ? progressEntries[0] ?? ''
      : progressEntries.map((text, i) => `── 投标 ${i + 1} ──\n${text}`).join('\n\n')

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
    // P3 上传阶段
    isUploading: uploadFilesMutation.isPending || isUploading,
    uploadProjectId,
    docsStatus: docsStatusQuery.data ?? null,
    tenderDocInfo: tenderDocInfoQuery.data ?? null,
    isOcrReady,
    hasFilesSelected,
    startUpload,
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
    openReport,
    batchDeleteProjects,
    batchRetryProjects,
    appendBidder,
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
  firstTenderFile: File
): TenderProjectCreateRequest {
  const title =
    form.title?.trim() || stripExtension(firstTenderFile.name) || '新建招投标项目'
  const tender_no =
    form.tender_no?.trim() || deriveTenderNo(firstTenderFile.name)
  return {
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
