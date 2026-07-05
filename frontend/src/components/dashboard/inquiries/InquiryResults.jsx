import RiskClassificationView from './RiskClassificationView'
import TimeSeriesAlertingView from './TimeSeriesAlertingView'
import OperationalTriageView from './OperationalTriageView'
import ExecutiveSummaryView from './ExecutiveSummaryView'

const VIEWS = [RiskClassificationView, TimeSeriesAlertingView, OperationalTriageView, ExecutiveSummaryView]

function InquiryResults({ activeIndex }) {
  const View = VIEWS[activeIndex]
  return <View />
}

export default InquiryResults
