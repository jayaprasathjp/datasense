import { getExecutiveSummary, HUB_TIERS, TIER_COLORS, REGION_COLORS } from '../../../data/mockData'
import DataTable from '../../ui/DataTable'
import StatTile from '../../ui/StatTile'
import GroupedBarChart from '../../charts/GroupedBarChart'
import RankedBarList from '../../charts/RankedBarList'
import BenchmarkStrip from '../BenchmarkStrip'
import SectionLabel from '../../ui/SectionLabel'
import { formatPercent } from '../../../lib/format'

const columns = [
  { key: 'region', header: 'Region' },
  { key: 'hub_tier', header: 'Hub Tier' },
  { key: 'total_shipments', header: 'Shipments', align: 'right' },
  {
    key: 'on_time_rate',
    header: 'On-Time Rate',
    align: 'right',
    render: (r) => formatPercent(r.on_time_rate),
  },
  {
    key: 'avg_delay_hours',
    header: 'Avg Delay (hrs)',
    align: 'right',
    render: (r) => r.avg_delay_hours.toFixed(0),
  },
  {
    key: 'breakdown_rate',
    header: 'Breakdown Rate',
    align: 'right',
    render: (r) => formatPercent(r.breakdown_rate),
  },
  {
    key: 'avg_sentiment',
    header: 'Avg Sentiment',
    align: 'right',
    render: (r) => r.avg_sentiment.toFixed(2),
  },
]

const shipmentFormatter = (v) => v.toLocaleString()

function ExecutiveSummaryView() {
  const { kpis, breakdown, shipmentsByRegion, breakdownRateByRegion, benchmark } =
    getExecutiveSummary()

  return (
    <div className="flex flex-col gap-8">
      <BenchmarkStrip {...benchmark} />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Total Shipments" value={kpis.total_shipments.toLocaleString()} />
        <StatTile label="On-Time Rate" value={formatPercent(kpis.on_time_rate)} />
        <StatTile label="Breakdown Rate" value={formatPercent(kpis.breakdown_rate)} />
        <StatTile label="Avg Sentiment" value={kpis.avg_sentiment.toFixed(2)} sublabel="range -1 to 1" />
      </div>

      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[3fr_2fr]">
        <div>
          <SectionLabel className="mb-4">Shipments by Region &amp; Hub Tier</SectionLabel>
          <GroupedBarChart
            data={shipmentsByRegion}
            seriesKeys={HUB_TIERS}
            colors={TIER_COLORS}
            valueFormatter={shipmentFormatter}
          />
        </div>
        <div>
          <SectionLabel className="mb-4">Breakdown Rate by Region</SectionLabel>
          <RankedBarList
            data={breakdownRateByRegion}
            labelKey="region"
            valueKey="value"
            colors={REGION_COLORS}
            valueFormatter={formatPercent}
          />
        </div>
      </div>

      <div>
        <SectionLabel className="mb-4">Full Breakdown</SectionLabel>
        <DataTable columns={columns} rows={breakdown} keyField="id" />
      </div>
    </div>
  )
}

export default ExecutiveSummaryView
