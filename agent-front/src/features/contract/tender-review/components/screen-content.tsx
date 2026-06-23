import type { useTenderReviewPage } from '../use-tender-review-page'
import { AnalysisWorkbenchView } from './analysis-workbench-view'
import { AnalyzingView } from './analyzing-view'
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
          onOpenProject={(projectId) => page.resumeOrOpenProject(projectId)}
          onCreateReview={() => page.setScreen('create')}
          onBatchDelete={page.batchDeleteProjects}
          onBatchRetry={page.batchRetryProjects}
          onAppendBidder={page.appendBidder}
        />
      )
    case 'create':
      return (
        <CreateReviewView
          projectForm={page.projectForm}
          tenderFiles={page.tenderFiles}
          uploadBidders={page.uploadBidders}
          progress={page.progress}
          isAnalyzing={page.isAnalyzing}
          isUploading={page.isUploading}
          uploadingTender={page.uploadingTender}
          uploadedBidderIds={page.uploadedBidderIds}
          uploadingBidderIds={page.uploadingBidderIds}
          isOcrReady={page.isOcrReady}
          hasUploaded={page.uploadProjectId !== null}
          docsStatus={page.docsStatus}
          uploadError={page.uploadError}
          submitError={page.submitError}
          canStart={page.canStartReview}
          onStart={page.startReview}
          onCancel={() => {
            page.resetProjectForm()
            page.setScreen('dashboard')
          }}
          onUpdateProjectForm={page.updateProjectForm}
          onAddTenderFile={page.addTenderFile}
          onRemoveTenderFile={page.removeTenderFile}
          onAddBidder={page.addBidder}
          onRemoveBidder={page.removeBidder}
          onUpdateBidderName={page.updateBidderName}
          onAddBidderFile={page.addBidderFile}
          onRemoveBidderFile={page.removeBidderFile}
        />
      )
    case 'analyzing':
      return (
        <AnalyzingView
          progress={page.progress}
          progressText={page.progressText}
          title={page.projectForm.title ?? undefined}
          projectForm={page.projectForm}
          docsStatus={page.docsStatus}
          tenderDocInfo={page.tenderDocInfo}
          onExit={page.exitAnalyzing}
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
          onAnalysis={(projectId) => page.resumeOrOpenProject(projectId)}
          onReport={(projectId) => page.openReport(projectId)}
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
          onHistory={() => page.openHistory()}
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
