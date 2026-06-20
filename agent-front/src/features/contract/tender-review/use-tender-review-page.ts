import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createTenderProject,
  evaluateTenderProjectUpload,
  getTenderCompareOrNull,
  getTenderProject,
  getTenderProjectResult,
  listTenderProjectResults,
  listTenderProjects,
  triggerTenderCompare,
  waitForTenderCompare,
  waitForTenderTask,
  type TenderProjectCreateRequest,
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

const TENDER_PROJECTS_QUERY_KEY = ['tender-projects'] as const
const EMPTY_PROJECT_TITLE = '新建招投标项目'
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

  const resultsQuery = useQuery({
    queryKey: ['tender-project-results', selectedProjectIdForQuery],
    queryFn: () => listTenderProjectResults(selectedProjectIdForQuery, { limit: 200 }),
    enabled: shouldLoadSelectedProject,
  })

  const compareQuery = useQuery({
    queryKey: ['tender-project-compare', selectedProjectIdForQuery],
    queryFn: () => getTenderCompareOrNull(selectedProjectIdForQuery),
    enabled: shouldLoadSelectedProject,
    refetchInterval: (query) => {
      const compare = query.state.data
      return compare == null || compare.stale ? 3000 : false
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
        : mapTenderProject(project)
    )
  }, [
    compareQuery.data,
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
    const project = await createTenderProject(buildCreateProjectBody(nativeTenderFiles[0]))
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
    tenderFiles,
    uploadBidders,
    canStartReview,
    startReview,
    addTenderFile,
    removeTenderFile,
    addBidder,
    removeBidder,
    updateBidderName,
    addBidderFile,
    removeBidderFile,
    openAnalysis,
    openReport,
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

function buildCreateProjectBody(file: File): TenderProjectCreateRequest {
  const title = stripExtension(file.name) || EMPTY_PROJECT_TITLE
  return {
    tender_no: deriveTenderNo(file.name),
    title,
    method: '综合评估法',
    funding_type: 'unknown',
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
