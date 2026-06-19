import { useMemo, useState } from 'react'
import { tenderReviewMockData } from './mock-data'
import { buildDashboardSummary, filterReviewHistory } from './model'
import type {
  HistoryTimeRange,
  ReviewCategory,
  TenderFile,
  TenderReviewScreen,
  TenderReviewMode,
  UploadBidder,
} from './types'

const PROGRESS_STEP = 4
const PROGRESS_INTERVAL_MS = 80

function toTenderFiles(files: FileList | null): TenderFile[] {
  if (!files?.length) return []
  return Array.from(files).map((file) => ({
    name: file.name,
    size: file.size,
    file,
  }))
}

export function useTenderReviewPage(
  initialScreen: TenderReviewScreen = 'dashboard'
) {
  const [screen, setScreen] = useState<TenderReviewScreen>(initialScreen)
  const [reviewMode, setReviewMode] = useState<TenderReviewMode>('detail')
  const [category, setCategory] = useState<ReviewCategory>('qual')
  const [selectedBidderId, setSelectedBidderId] = useState('A')
  const [activeItemId, setActiveItemId] = useState('q4')
  const [query, setQuery] = useState('')
  const [timeRange, setTimeRange] = useState<HistoryTimeRange>('all')
  const [progress, setProgress] = useState(0)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [uploadError, setUploadError] = useState(false)
  const [tenderFiles, setTenderFiles] = useState<TenderFile[]>(
    tenderReviewMockData.tenderFiles
  )
  const [uploadBidders, setUploadBidders] = useState<UploadBidder[]>(
    tenderReviewMockData.uploadBidders
  )
  const [nextBidderId, setNextBidderId] = useState(
    tenderReviewMockData.uploadBidders.length + 1
  )

  const summary = useMemo(() => buildDashboardSummary(tenderReviewMockData), [])
  const history = useMemo(
    () =>
      filterReviewHistory(tenderReviewMockData.projects, {
        query,
        timeRange,
        now: '2026-06-19',
      }),
    [query, timeRange]
  )

  const canStartReview =
    tenderFiles.length > 0 &&
    uploadBidders.some((bidder) => bidder.files.length > 0)

  function openAnalysis(mode: TenderReviewMode = 'detail') {
    setReviewMode(mode)
    setScreen('analysis')
  }

  function openReport() {
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
    if (isAnalyzing) return
    if (!canStartReview) {
      setUploadError(true)
      return
    }

    setIsAnalyzing(true)
    setUploadError(false)
    setProgress(0)
    const timer = window.setInterval(() => {
      setProgress((current) => {
        const next = Math.min(100, current + PROGRESS_STEP)
        if (next >= 100) {
          window.clearInterval(timer)
          window.setTimeout(() => {
            setIsAnalyzing(false)
            setReviewMode('detail')
            setScreen('analysis')
            setProgress(0)
          }, 450)
        }
        return next
      })
    }, PROGRESS_INTERVAL_MS)
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
    isAnalyzing,
    uploadError,
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
      data: tenderReviewMockData,
    },
  }
}
