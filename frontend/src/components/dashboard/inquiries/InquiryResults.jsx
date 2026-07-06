import RiskClassificationView from './RiskClassificationView'
import TimeSeriesAlertingView from './TimeSeriesAlertingView'
import OperationalTriageView from './OperationalTriageView'
import ExecutiveSummaryView from './ExecutiveSummaryView'
import LiveResultsView from './LiveResultsView'

const MOCK_VIEWS = [
  RiskClassificationView,
  TimeSeriesAlertingView,
  OperationalTriageView,
  ExecutiveSummaryView,
]

function InquiryResults({ activeIndex, apiResult }) {
  // If we have a real API result, render the live generic view
  if (apiResult) {
    return <LiveResultsView apiResult={apiResult} />
  }

  // Fallback to mock views before first run
  const View = MOCK_VIEWS[activeIndex]
  return <View />
}

export default InquiryResults
