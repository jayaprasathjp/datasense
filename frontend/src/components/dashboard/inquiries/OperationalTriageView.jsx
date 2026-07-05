import { getOperationalTriage } from '../../../data/mockData'
import DataTable from '../../ui/DataTable'
import Badge from '../../ui/Badge'
import Meter from '../../ui/Meter'
import BenchmarkStrip from '../BenchmarkStrip'
import { formatCurrency } from '../../../lib/format'

const priorityTone = (score) => (score >= 0.66 ? 'critical' : score >= 0.4 ? 'warning' : 'good')

const columns = [
  { key: 'rank', header: '#', align: 'right' },
  { key: 'shipment_id', header: 'Shipment' },
  { key: 'hub_name', header: 'Hub' },
  {
    key: 'vehicle_breakdown_flag',
    header: 'Vehicle Breakdown',
    render: (r) =>
      r.vehicle_breakdown_flag ? (
        <Badge tone="critical">Yes</Badge>
      ) : (
        <Badge tone="good">No</Badge>
      ),
  },
  {
    key: 'weather_severity',
    header: 'Weather Severity',
    align: 'right',
    render: (r) => r.weather_severity.toFixed(2),
  },
  {
    key: 'ticket_age_hours',
    header: 'Ticket Age (hrs)',
    align: 'right',
    render: (r) => r.ticket_age_hours.toFixed(0),
  },
  { key: 'sentiment', header: 'Sentiment', align: 'right', render: (r) => r.sentiment.toFixed(2) },
  {
    key: 'delay_cost',
    header: 'Delay Cost',
    align: 'right',
    render: (r) => formatCurrency(r.delay_cost),
  },
  {
    key: 'priority_score',
    header: 'Priority',
    render: (r) => (
      <Meter
        value={r.priority_score}
        tone={priorityTone(r.priority_score)}
        label={`${(r.priority_score * 100).toFixed(0)}%`}
      />
    ),
  },
]

function OperationalTriageView() {
  const { rows, benchmark } = getOperationalTriage()

  return (
    <div className="flex flex-col gap-6">
      <BenchmarkStrip {...benchmark} />
      <DataTable columns={columns} rows={rows} />
    </div>
  )
}

export default OperationalTriageView
