import { getRiskClassification } from '../../../data/mockData'
import DataTable from '../../ui/DataTable'
import Meter from '../../ui/Meter'
import Badge from '../../ui/Badge'
import BenchmarkStrip from '../BenchmarkStrip'

const riskTone = (label) =>
  label === 'High Risk' ? 'critical' : label === 'Medium Risk' ? 'warning' : 'good'

const columns = [
  { key: 'rank', header: '#', align: 'right' },
  { key: 'shipment_id', header: 'Shipment' },
  {
    key: 'hub_name',
    header: 'Hub',
    render: (r) => (
      <>
        {r.hub_name}
        <span className="ml-1.5 text-xs text-zinc-400">{r.region}</span>
      </>
    ),
  },
  {
    key: 'weather_severity',
    header: 'Weather Severity',
    align: 'right',
    render: (r) => r.weather_severity.toFixed(2),
  },
  {
    key: 'transit_hours',
    header: 'Transit (hrs)',
    align: 'right',
    render: (r) => r.transit_hours.toFixed(0),
  },
  {
    key: 'ticket_age_hours',
    header: 'Ticket Age (hrs)',
    align: 'right',
    render: (r) => r.ticket_age_hours.toFixed(0),
  },
  {
    key: 'risk_label',
    header: 'Risk Label',
    render: (r) => <Badge tone={riskTone(r.risk_label)}>{r.risk_label}</Badge>,
  },
  {
    key: 'pred_risk',
    header: 'Pred. Risk',
    render: (r) => (
      <Meter
        value={r.pred_risk}
        tone={riskTone(r.risk_label)}
        label={`${(r.pred_risk * 100).toFixed(1)}%`}
      />
    ),
  },
]

function RiskClassificationView() {
  const { rows, benchmark } = getRiskClassification()

  return (
    <div className="flex flex-col gap-6">
      <BenchmarkStrip {...benchmark} />
      <DataTable columns={columns} rows={rows} />
    </div>
  )
}

export default RiskClassificationView
