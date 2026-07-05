// Mock data layer for the FleetPulse GPU inquiry dashboards.
//
// Every getX() below returns the same shape a real backend endpoint should
// return once the RAPIDS pipeline is wired up. Swap the body for a fetch():
//   getRiskClassification()  -> GET /api/inquiries/risk-classification
//   getTimeSeriesAlerts()    -> GET /api/inquiries/time-series-alerting
//   getOperationalTriage()   -> GET /api/inquiries/operational-triage
//   getExecutiveSummary()    -> GET /api/inquiries/executive-summary
// Source dataset: global_logistics_network shipment events (181K rows).

function mulberry32(seed) {
  return function () {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.min(Math.imul(seed ^ (seed >>> 15), 1 | seed))
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const rand = mulberry32(42)
const randRange = (min, max) => min + rand() * (max - min)
const randInt = (min, max) => Math.floor(randRange(min, max + 1))
const pick = (arr) => arr[Math.floor(rand() * arr.length)]
const clamp01 = (n) => Math.max(0, Math.min(1, n))

export const REGIONS = ['North America', 'Europe', 'APAC', 'LATAM']
export const REGION_COLORS = {
  'North America': '#4f46e5',
  Europe: '#b45309',
  APAC: '#0d9488',
  LATAM: '#9d174d',
}

export const HUB_TIERS = ['Primary', 'Regional', 'Satellite']
export const TIER_COLORS = {
  Primary: '#4f46e5',
  Regional: '#0d9488',
  Satellite: '#b45309',
}

const HUB_NAMES = [
  'Port Gateway Hub',
  'Continental Crossdock',
  'Riverside Distribution Center',
  'Highland Freight Terminal',
  'Bayshore Sorting Facility',
  'Union Rail Yard',
  'Metro Fulfillment Center',
  'Ironbridge Depot',
  'Lakeside Cargo Hub',
  'Granary Logistics Park',
  'Northgate Transfer Station',
  'Eastside Consolidation Center',
  'Westfield Air Cargo Terminal',
  'Old Mill Warehouse',
  'Harborview Customs Depot',
  'Southport Intermodal Yard',
]

const HUBS = HUB_NAMES.map((name, i) => ({
  hub_id: `HB-${100 + i}`,
  hub_name: name,
  region: REGIONS[i % REGIONS.length],
  hub_tier: HUB_TIERS[(i + 1) % HUB_TIERS.length],
}))

// --- base shipment-level dataset (feeds Risk Classification & Operational Triage) ---

const ROW_COUNT = 320

const BASE_ROWS = Array.from({ length: ROW_COUNT }, (_, i) => {
  const hub = pick(HUBS)
  const transit_hours = Number(randRange(4, 96).toFixed(1))
  const weather_severity = Number(randRange(0, 1).toFixed(2))
  const vehicle_breakdown_flag = rand() < 0.13
  // right-skewed: most tickets close fast, a long tail drives the bottleneck cases
  const ticket_age_hours = Number((rand() ** 3 * 260).toFixed(1))
  const sentiment = Number(randRange(-1, 1).toFixed(2))
  const delay_cost = Number(randRange(15, 620).toFixed(2))

  const transitNorm = clamp01(transit_hours / 96)
  const ticketNorm = clamp01(ticket_age_hours / 260)
  const sentimentNorm = clamp01((sentiment + 1) / 2)

  const riskLatent = clamp01(
    0.3 * weather_severity +
      0.25 * (vehicle_breakdown_flag ? 1 : 0) +
      0.25 * ticketNorm +
      0.1 * transitNorm +
      0.1 * (1 - sentimentNorm)
  )

  const pred_risk = Number(clamp01(riskLatent + randRange(-0.06, 0.06)).toFixed(3))
  const risk_label =
    pred_risk >= 0.7 ? 'High Risk' : pred_risk >= 0.45 ? 'Medium Risk' : 'Low Risk'

  // most shipments arrive on time; only the higher-risk tail slips
  const on_time = riskLatent < 0.5

  const daysAgo = randInt(0, 29)
  const created_at = new Date(Date.now() - daysAgo * 86400000).toISOString().slice(0, 10)

  return {
    shipment_id: `SHP-${100000 + i}`,
    hub_id: hub.hub_id,
    hub_name: hub.hub_name,
    region: hub.region,
    hub_tier: hub.hub_tier,
    transit_hours,
    weather_severity,
    vehicle_breakdown_flag,
    ticket_age_hours,
    sentiment,
    delay_cost,
    pred_risk,
    risk_label,
    on_time,
    created_at,
  }
})

/** Q1 — Risk Classification (RF)
 *  "Train a classifier to predict delay_risk_label from numeric features
 *   and return the top 20 highest-risk shipments with pred_risk probability." */
export function getRiskClassification() {
  const rows = [...BASE_ROWS]
    .sort((a, b) => b.pred_risk - a.pred_risk)
    .slice(0, 20)
    .map((r, i) => ({ rank: i + 1, ...r }))

  return {
    rows,
    benchmark: { cpuSeconds: 81.04, gpuSeconds: 0.38, note: 'rf_classify_fit @ 181K rows' },
  }
}

// --- daily hub parcel volume (feeds Time-Series Alerting) ---

const SERIES_DAYS = 21
const SPIKE_HUB_COUNT = 10
const spikeHubIds = new Set(HUBS.slice(0, SPIKE_HUB_COUNT).map((h) => h.hub_id))

const HUB_VOLUME_SERIES = HUBS.map((hub) => {
  const base = randRange(900, 3200)
  const days = Array.from({ length: SERIES_DAYS }, (_, d) => {
    const noise = randRange(-0.12, 0.12)
    let volume = base * (1 + noise)
    const isLastDay = d === SERIES_DAYS - 1
    if (isLastDay && spikeHubIds.has(hub.hub_id)) {
      const spike = randRange(0.32, 0.68)
      volume = base * (1 + spike)
    }
    return Math.round(volume)
  })
  return { hub, days }
})

function rollingAverage(days, windowEndIndex, windowSize = 7) {
  const start = Math.max(0, windowEndIndex - windowSize + 1)
  const window = days.slice(start, windowEndIndex + 1)
  return window.reduce((sum, v) => sum + v, 0) / window.length
}

/** Q2 — Time-Series Alerting
 *  "Compute a 7-day rolling average parcel volume per distribution hub.
 *   Flag the top 10 hubs where today's volume is more than 30% above
 *   the rolling average." */
export function getTimeSeriesAlerts() {
  const lastIndex = SERIES_DAYS - 1
  const rows = HUB_VOLUME_SERIES.map(({ hub, days }) => {
    const today_volume = days[lastIndex]
    const rolling_avg_volume = Math.round(rollingAverage(days, lastIndex - 1))
    const pct_vs_rolling = Number(
      (((today_volume - rolling_avg_volume) / rolling_avg_volume) * 100).toFixed(1)
    )
    return {
      hub_id: hub.hub_id,
      hub_name: hub.hub_name,
      region: hub.region,
      today_volume,
      rolling_avg_volume,
      pct_vs_rolling,
      sparkline: days,
    }
  })
    .filter((r) => r.pct_vs_rolling >= 30)
    .sort((a, b) => b.pct_vs_rolling - a.pct_vs_rolling)
    .slice(0, 10)
    .map((r, i) => ({ rank: i + 1, ...r }))

  return {
    rows,
    benchmark: { cpuSeconds: 0.1, gpuSeconds: 0.13, note: 'rolling_window @ 181K rows (20M-row sweep: 58.9x)' },
  }
}

/** Q3 — Operational Triage
 *  "Rank the top 25 shipments by operational priority using
 *   vehicle_breakdown_flag, ticket_age_hours, weather_severity,
 *   sentiment, and delay_cost." */
export function getOperationalTriage() {
  const ticketMax = Math.max(...BASE_ROWS.map((r) => r.ticket_age_hours))
  const delayCostMax = Math.max(...BASE_ROWS.map((r) => r.delay_cost))

  const rows = BASE_ROWS.map((r) => {
    const sentimentNorm = clamp01((r.sentiment + 1) / 2)
    const priority_score = clamp01(
      0.28 * (r.ticket_age_hours / ticketMax) +
        0.22 * r.weather_severity +
        0.22 * (r.vehicle_breakdown_flag ? 1 : 0) +
        0.14 * (1 - sentimentNorm) +
        0.14 * (r.delay_cost / delayCostMax)
    )
    return { ...r, priority_score: Number(priority_score.toFixed(3)) }
  })
    .sort((a, b) => b.priority_score - a.priority_score)
    .slice(0, 25)
    .map((r, i) => ({ rank: i + 1, ...r }))

  return {
    rows,
    benchmark: { cpuSeconds: 0.04, gpuSeconds: 0.63, note: 'vectorized priority scoring @ 181K rows' },
  }
}

/** Q4 — Executive Summary
 *  "Create a dashboard summary grouped by region and hub_tier showing
 *   total shipments, on-time rate, avg delay, vehicle breakdown rate,
 *   and avg sentiment." */
export function getExecutiveSummary() {
  const groups = {}
  for (const r of BASE_ROWS) {
    const key = `${r.region}::${r.hub_tier}`
    if (!groups[key]) {
      groups[key] = { region: r.region, hub_tier: r.hub_tier, rows: [] }
    }
    groups[key].rows.push(r)
  }

  const breakdown = Object.values(groups).map((g) => {
    const n = g.rows.length
    const total_shipments = n
    const on_time_rate = g.rows.filter((r) => r.on_time).length / n
    const avg_delay_hours = g.rows.reduce((s, r) => s + r.ticket_age_hours, 0) / n
    const breakdown_rate = g.rows.filter((r) => r.vehicle_breakdown_flag).length / n
    const avg_sentiment = g.rows.reduce((s, r) => s + r.sentiment, 0) / n
    return {
      id: `${g.region}::${g.hub_tier}`,
      region: g.region,
      hub_tier: g.hub_tier,
      total_shipments,
      on_time_rate: Number(on_time_rate.toFixed(3)),
      avg_delay_hours: Number(avg_delay_hours.toFixed(1)),
      breakdown_rate: Number(breakdown_rate.toFixed(3)),
      avg_sentiment: Number(avg_sentiment.toFixed(2)),
    }
  })

  const shipmentsByRegion = REGIONS.map((region) => {
    const entry = { region }
    for (const tier of HUB_TIERS) {
      const match = breakdown.find((b) => b.region === region && b.hub_tier === tier)
      entry[tier] = match ? match.total_shipments : 0
    }
    return entry
  })

  const breakdownRateByRegion = REGIONS.map((region) => {
    const rows = BASE_ROWS.filter((r) => r.region === region)
    return {
      region,
      value: Number(
        (rows.filter((r) => r.vehicle_breakdown_flag).length / rows.length).toFixed(3)
      ),
    }
  })

  const n = BASE_ROWS.length
  const kpis = {
    total_shipments: n,
    on_time_rate: Number((BASE_ROWS.filter((r) => r.on_time).length / n).toFixed(3)),
    breakdown_rate: Number(
      (BASE_ROWS.filter((r) => r.vehicle_breakdown_flag).length / n).toFixed(3)
    ),
    avg_sentiment: Number((BASE_ROWS.reduce((s, r) => s + r.sentiment, 0) / n).toFixed(2)),
  }

  return {
    kpis,
    breakdown: breakdown.sort((a, b) => b.total_shipments - a.total_shipments),
    shipmentsByRegion,
    breakdownRateByRegion,
    benchmark: { cpuSeconds: 0.03, gpuSeconds: 0.21, note: 'groupby_agg @ 181K rows (20M-row sweep: 14x)' },
  }
}

// --- LLM-synthesized code shown in the "Synthesized Logic" panel, per inquiry ---

export const CODE_SNIPPETS = {
  riskClassification: {
    cpu: `from sklearn.ensemble import RandomForestClassifier

model = RandomForestClassifier(n_estimators=200)
model.fit(X_train, y_train)

proba = model.predict_proba(X_test)[:, 1]
top20 = X_test.assign(pred_risk=proba) \\
    .sort_values('pred_risk', ascending=False) \\
    .head(20)`,
    gpu: `import cudf
from cuml.ensemble import RandomForestClassifier

X_train = cudf.DataFrame.from_pandas(X_train)
model = RandomForestClassifier(n_estimators=200)
model.fit(X_train, y_train)

proba = model.predict_proba(X_test)[1]
top20 = X_test.assign(pred_risk=proba) \\
    .sort_values('pred_risk', ascending=False) \\
    .head(20)`,
  },
  timeSeriesAlerting: {
    cpu: `df['rolling_avg'] = (
    df.groupby('hub_id')['volume']
      .transform(lambda s: s.rolling(7, min_periods=1).mean())
)
df['pct_vs_rolling'] = (df['volume'] - df['rolling_avg']) / df['rolling_avg']
flagged = df[df['pct_vs_rolling'] >= 0.30] \\
    .nlargest(10, 'pct_vs_rolling')`,
    gpu: `gdf = cudf.from_pandas(df)
gdf['rolling_avg'] = (
    gdf.groupby('hub_id')['volume']
       .rolling(7, min_periods=1).mean()
       .reset_index(drop=True)
)
gdf['pct_vs_rolling'] = (gdf['volume'] - gdf['rolling_avg']) / gdf['rolling_avg']
flagged = gdf[gdf['pct_vs_rolling'] >= 0.30] \\
    .nlargest(10, 'pct_vs_rolling')`,
  },
  operationalTriage: {
    cpu: `w = dict(age=0.28, weather=0.22, breakdown=0.22, sentiment=0.14, cost=0.14)

df['priority_score'] = (
    w['age'] * (df.ticket_age_hours / df.ticket_age_hours.max()) +
    w['weather'] * df.weather_severity +
    w['breakdown'] * df.vehicle_breakdown_flag.astype(int) +
    w['sentiment'] * (1 - (df.sentiment + 1) / 2) +
    w['cost'] * (df.delay_cost / df.delay_cost.max())
)
top25 = df.nlargest(25, 'priority_score')`,
    gpu: `gdf = cudf.from_pandas(df)
gdf['priority_score'] = (
    0.28 * (gdf.ticket_age_hours / gdf.ticket_age_hours.max()) +
    0.22 * gdf.weather_severity +
    0.22 * gdf.vehicle_breakdown_flag.astype('int32') +
    0.14 * (1 - (gdf.sentiment + 1) / 2) +
    0.14 * (gdf.delay_cost / gdf.delay_cost.max())
)
top25 = gdf.nlargest(25, 'priority_score')`,
  },
  executiveSummary: {
    cpu: `summary = df.groupby(['region', 'hub_tier']).agg(
    total_shipments=('shipment_id', 'count'),
    on_time_rate=('on_time', 'mean'),
    avg_delay_hours=('ticket_age_hours', 'mean'),
    breakdown_rate=('vehicle_breakdown_flag', 'mean'),
    avg_sentiment=('sentiment', 'mean'),
).reset_index()`,
    gpu: `gdf = cudf.from_pandas(df)
summary = gdf.groupby(['region', 'hub_tier']).agg({
    'shipment_id': 'count',
    'on_time': 'mean',
    'ticket_age_hours': 'mean',
    'vehicle_breakdown_flag': 'mean',
    'sentiment': 'mean',
}).reset_index()`,
  },
}
