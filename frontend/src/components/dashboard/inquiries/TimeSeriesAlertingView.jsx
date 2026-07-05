import { getTimeSeriesAlerts } from '../../../data/mockData'
import DataTable from '../../ui/DataTable'
import Badge from '../../ui/Badge'
import BenchmarkStrip from '../BenchmarkStrip'
import { formatSigned } from '../../../lib/format'

function Sparkline({ days }) {
  const max = Math.max(...days)
  const min = Math.min(...days)
  const range = max - min || 1
  const points = days
    .map((v, i) => {
      const x = (i / (days.length - 1)) * 100
      const y = 24 - ((v - min) / range) * 24
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg viewBox="0 0 100 24" preserveAspectRatio="none" className="h-6 w-24">
      <polyline points={points} fill="none" stroke="#4f46e5" strokeWidth="2" />
      <circle
        cx={100}
        cy={24 - ((days[days.length - 1] - min) / range) * 24}
        r="3"
        fill="#dc2626"
        stroke="#ffffff"
        strokeWidth="2"
      />
    </svg>
  )
}

const columns = [
  { key: 'rank', header: '#', align: 'right' },
  { key: 'hub_name', header: 'Hub' },
  { key: 'region', header: 'Region' },
  { key: 'sparkline', header: '21-Day Trend', render: (r) => <Sparkline days={r.sparkline} /> },
  {
    key: 'rolling_avg_volume',
    header: '7-Day Rolling Avg',
    align: 'right',
    render: (r) => r.rolling_avg_volume.toLocaleString(),
  },
  {
    key: 'today_volume',
    header: "Today's Volume",
    align: 'right',
    render: (r) => r.today_volume.toLocaleString(),
  },
  {
    key: 'pct_vs_rolling',
    header: 'Vs. Rolling Avg',
    align: 'right',
    render: (r) => (
      <span className="font-semibold" style={{ color: '#dc2626' }}>
        {formatSigned(r.pct_vs_rolling)}
      </span>
    ),
  },
  {
    key: 'flag',
    header: 'Status',
    render: () => <Badge tone="critical">Spike Flagged</Badge>,
  },
]

function TimeSeriesAlertingView() {
  const { rows, benchmark } = getTimeSeriesAlerts()

  return (
    <div className="flex flex-col gap-6">
      <BenchmarkStrip {...benchmark} />
      <DataTable columns={columns} rows={rows} />
    </div>
  )
}

export default TimeSeriesAlertingView
