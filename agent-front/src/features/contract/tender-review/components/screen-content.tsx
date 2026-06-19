import type { useTenderReviewPage } from '../use-tender-review-page'
import { AnalysisWorkbenchView } from './analysis-workbench-view'
import { CreateReviewView } from './create-review-view'
import { DashboardView } from './dashboard-view'
import { HistoryView } from './history-view'
import { ReportView } from './report-view'

type TenderReviewPageState = ReturnType<typeof useTenderReviewPage>

export function ScreenContent({ page }: { page: TenderReviewPageState }) {
  switch (page.screen) {
    case 'dashboard':
      return (
        <DashboardView
          summary={page.viewModel.summary}
          projects={page.viewModel.data.projects}
          onOpenProject={() => page.openAnalysis('detail')}
        />
      )
    case 'create':
      return (
        <CreateReviewView
          projectInfo={page.viewModel.data.projectInfo}
          tenderFiles={page.tenderFiles}
          uploadBidders={page.uploadBidders}
          progress={page.progress}
          isAnalyzing={page.isAnalyzing}
          uploadError={page.uploadError}
          canStart={page.canStartReview}
          onStart={page.startReview}
          onCancel={() => page.setScreen('dashboard')}
          onAddTenderFile={page.addTenderFile}
          onRemoveTenderFile={page.removeTenderFile}
          onAddBidder={page.addBidder}
          onRemoveBidder={page.removeBidder}
          onUpdateBidderName={page.updateBidderName}
          onAddBidderFile={page.addBidderFile}
          onRemoveBidderFile={page.removeBidderFile}
        />
      )
    case 'history':
      return (
        <HistoryView
          query={page.query}
          timeRange={page.timeRange}
          history={page.viewModel.history}
          onQuery={page.setQuery}
          onTimeRange={page.setTimeRange}
          onAnalysis={() => page.openAnalysis('detail')}
          onReport={page.openReport}
        />
      )
    case 'analysis':
      return (
        <AnalysisWorkbenchView
          data={page.viewModel.data}
          mode={page.reviewMode}
          category={page.category}
          selectedBidderId={page.selectedBidderId}
          activeItemId={page.activeItemId}
          onMode={page.setReviewMode}
          onCategory={page.setCategory}
          onBidder={page.setSelectedBidderId}
          onActiveItem={page.setActiveItemId}
          onHistory={() => page.setScreen('history')}
          onReport={page.openReport}
        />
      )
    case 'report':
      return (
        <ReportView
          data={page.viewModel.data}
          onBack={() => page.openAnalysis('compare')}
        />
      )
  }
}
