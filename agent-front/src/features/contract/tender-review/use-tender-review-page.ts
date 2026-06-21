import { useMemo, useState } from 'react'
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
  getTenderCompareOrNull,
  getTenderProject,
  getTenderProjectResult,
  listTenderProjectResults,
  listTenderProjects,
  retryTenderTask,
  triggerTenderCompare,
  waitForTenderCompare,
  waitForTenderTask,
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
  const [screen, setScreen] = useState<TenderReviewScreen>(initialScreen)
  const [reviewMode, setReviewMode] = useState<TenderReviewMode>('detail')
  const [category, setCategory] = useState<ReviewCategory>('qual')
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [selectedBidderId, setSelectedBidderId] = useState('')
  const [activeItemId, setActiveItemId] = useState('result-summary')
  const [query, setQuery] = useState('')
  const [timeRange, setTimeRange] = useState<HistoryTimeRange>('all')
  const [progress, setProgress] = useState(0)
  const [uploadError, setUploadError] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [tenderFiles, setTenderFiles] = useState<TenderFile[]>([])
  const [uploadBidders, setUploadBidders] = useState<UploadBidder[]>([
    DEFAULT_UPLOAD_BIDDER,
  ])
  const [nextBidderId, setNextBidderId] = useState(2)

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

  const canStartReview =
    tenderFiles.some(hasNativeFile) &&
    uploadBidders.some((bidder) => bidder.files.some(hasNativeFile))

  const startReviewMutation = useMutation({
    mutationFn: submitReview,
    onSuccess: async ({ projectId, hasCompare }) => {
      setSelectedProjectId(projectId)
      setReviewMode(hasCompare ? 'compare' : 'detail')
      setScreen('analysis')
      await queryClient.invalidateQueries({ queryKey: TENDER_PROJECTS_QUERY_KEY })
      await queryClient.invalidateQueries({ queryKey: ['tender-project', projectId] })
      await queryClient.invalidateQueries({
        queryKey: ['tender-project-results', projectId],
      })
      await queryClient.invalidateQueries({
        queryKey: ['tender-project-compare', projectId],
      })
      setProgress(0)
    },
    onError: (error) => {
      setSubmitError(error instanceof Error ? error.message : '分析失败，请稍后重试。')
      setProgress(0)
      setScreen('create') // 乐观跳 analyzing 后提交失败 → 回 create 显示错误，让用户重试
    },
  })

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
    setScreen('analyzing') // 乐观跳第三步"开始分析"界面；提交在后台跑，失败由 onError 回 create
    startReviewMutation.mutate()
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

    setProgress(4)
    // A①: pass all 6 user-supplied project fields into createTenderProject body
    const project = await createTenderProject(
      buildCreateProjectBody(projectForm, nativeTenderFiles[0])
    )
    setProgress(10)

    const acceptedTasks = []
    for (const [index, bidder] of bidders.entries()) {
      const accepted = await evaluateTenderProjectUpload(project.project_id, {
        bidderName: bidder.name,
        tenderFiles: nativeTenderFiles,
        bidderFiles: bidder.nativeFiles,
      })
      acceptedTasks.push(accepted)
      setProgress(10 + Math.round(((index + 1) / bidders.length) * 20))
    }

    let completedCount = 0
    await Promise.all(
      acceptedTasks.map((task) =>
        waitForTenderTask(task.request_id, {
          onUpdate: (status) => {
            if (status.progress_message) {
              setSubmitError('')
            }
          },
        }).then((status) => {
          completedCount += 1
          setProgress(30 + Math.round((completedCount / acceptedTasks.length) * 50))
          return status
        })
      )
    )

    const hasCompare = acceptedTasks.length >= 2
    if (hasCompare) {
      setProgress(84)
      await triggerCompareOrContinue(project.project_id)
      setProgress(90)
      await waitForTenderCompare(project.project_id, {
        onUpdate: () => setProgress((current) => Math.max(current, 92)),
      })
    }

    setProgress(100)
    return { projectId: project.project_id, hasCompare }
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
    isAnalyzing: startReviewMutation.isPending,
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

async function triggerCompareOrContinue(projectId: string) {
  try {
    await triggerTenderCompare(projectId)
  } catch (error) {
    const message = error instanceof Error ? error.message : ''
    if (!message.includes('横比正在进行中')) throw error
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
