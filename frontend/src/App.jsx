import { Fragment, useEffect, useRef, useState } from 'react'
import { getDatasetInfo, runBenchmark } from './api/client'
import './index.css'

const TASK_TYPES = [
  { value: 'classification', label: 'Classification' },
  { value: 'rolling_window', label: 'Rolling window / alerting' },
  { value: 'ranking', label: 'Ranking / triage' },
  { value: 'data_analysis', label: 'Aggregation / summary' },
]

const INQUIRIES = [
  {
    label: 'Risk Classification (RF)',
    query: 'Train a classifier to predict risk_label from numeric columns (feat_1 to feat_4, price, qty, discount_pct, ticket_age_hours, sentiment, days_since_restock). Return the top 20 highest-risk rows with predicted probability as a new column called pred_risk.',
    task_type: 'classification',
    resultsTitle: 'Risk Classification Output',
  },
  {
    label: 'Time-Series Alerting',
    query: "Compute a 7-day rolling average revenue per store. Flag the top 10 stores where today's revenue is more than 20% below the rolling average. Return a dataframe of those anomalies.",
    task_type: 'rolling_window',
    resultsTitle: 'Anomalous Revenue Deterioration',
  },
  {
    label: 'Operational Triage',
    query: 'Rank the top 25 rows by operational priority using return_flag, ticket_age_hours, days_since_restock, sentiment, and margin. Add a priority_score column and return the ranked dataframe.',
    task_type: 'ranking',
    resultsTitle: 'Operational Triage Matrix',
  },
  {
    label: 'Executive Summary',
    query: 'Create an aggregated dashboard summary grouped by region and support_tier. Show total revenue, average margin, return rate, average ticket_age_hours, and average sentiment.',
    task_type: 'data_analysis',
    resultsTitle: 'Cross-Regional Performance Extract',
  },
]

const STEPS = ['Acquisition', 'Synthesis (LLM)', 'CPU Baseline', 'GPU Acceleration', 'Resolution']

// Kaggle sweep results (static reference data from notebook Section D)
const SWEEP_DATA = [
  { label: 'Time-series alerting', sub: 'rolling_window', val: 58.9, pct: 100, type: 'gpu' },
  { label: 'Dashboard enrichment', sub: 'merge_join', val: 39.8, pct: 67, type: 'gpu' },
  { label: 'Priority ranking', sub: 'sort_values', val: 21.1, pct: 36, type: 'ink' },
  { label: 'BI aggregation', sub: 'groupby_agg', val: 18.4, pct: 31, type: 'ink' },
  { label: 'Risk modeling (5M)', sub: 'rf_classify_fit', val: 15.7, pct: 27, type: 'ink' },
  { label: 'Forecasting', sub: 'linreg_fit', val: 11.7, pct: 20, type: 'ink' },
  { label: 'Segmentation (weak)', sub: 'kmeans_fit', val: 3.0, pct: 5, type: 'slow' },
]

function formatVal(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'number') return Number.isInteger(val) ? val.toLocaleString() : parseFloat(val.toFixed(4)).toString()
  return String(val)
}

// Backend rank/recommendation bands are always phrased from most- to least-urgent
// (see backend/app/services/risk_ranking.py) — map that language to a tone color
// rather than duplicating the band thresholds on the frontend.
function recommendationTone(text) {
  const t = String(text).toLowerCase()
  if (t.includes('immediately') || t.includes('escalate') || t.includes('handle first')) return 'danger'
  if (t.includes('soon') || t.includes('high priority') || t.includes('elevated')) return 'warning'
  if (t.includes('monitor') || t.includes('standard priority')) return 'accent'
  return 'success'
}

// Reliability signal derived from how many attempts the backend needed to
// produce this answer (see backend/app/services/modal_sandbox.py::confidence_from_attempts).
// The backend already picks the tier — this just paints it.
function ConfidenceBadge({ attemptsUsed, confidence }) {
  if (!confidence || !attemptsUsed) return null
  const tone = confidence === 'high' ? 'success' : confidence === 'medium' ? 'warning' : 'danger'
  const label = attemptsUsed === 1 ? '1st-try' : `${attemptsUsed} attempts`
  return (
    <span
      className={`rec-pill rec-${tone}`}
      title={`Succeeded after ${attemptsUsed} attempt${attemptsUsed > 1 ? 's' : ''} — ${confidence} confidence`}
    >
      {label}
    </span>
  )
}

// One-line plain-language bridge between "here is a dataframe" and "here is
// an insight" — see backend/app/services/insight_summary.py for how the
// sentence is derived.
function SummaryCard({ text }) {
  if (!text) return null
  return (
    <div className="summary-card">
      <span className="summary-badge">Insight</span>
      <p className="summary-text">{text}</p>
    </div>
  )
}

function ResultsTable({ rows }) {
  if (!rows || rows.length === 0) return (
    <p style={{ fontFamily: 'var(--sans)', fontSize: '0.82rem', color: 'var(--text-faint)' }}>
      No tabular output returned for this query.
    </p>
  )
  const columns = Object.keys(rows[0])
  return (
    <div className="table-container">
      <table>
        <thead>
          <tr>
            {columns.map(col => (
              <th key={col} className={col === 'rank' ? 'rank-col' : col === 'recommendation' ? '' : 'n'}>
                {col === 'rank' ? '#' : col.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 25).map((row, i) => (
            <tr key={i}>
              {columns.map(col => {
                if (col === 'rank') {
                  return <td key={col} className="rank-col"><span className="rank-badge">{row[col]}</span></td>
                }
                if (col === 'recommendation') {
                  return (
                    <td key={col}>
                      <span className={`rec-pill rec-${recommendationTone(row[col])}`}>{row[col]}</span>
                    </td>
                  )
                }
                return <td key={col} className="n">{formatVal(row[col])}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SearchIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}

export default function App() {
  const [query, setQuery] = useState(INQUIRIES[0].query)
  const [taskType, setTaskType] = useState(INQUIRIES[0].task_type)
  const [stepIdx, setStepIdx] = useState(STEPS.length - 1)
  const [isRunning, setIsRunning] = useState(false)
  const [apiResult, setApiResult] = useState(null)
  const [apiError, setApiError] = useState(null)
  const [debugLines, setDebugLines] = useState([{ cls: 'dl-sys', text: 'System initialized. Awaiting parameters.' }])
  const [showSpeedup, setShowSpeedup] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const [chartsVisible, setChartsVisible] = useState(false)
  const [datasetInfo, setDatasetInfo] = useState(null)
  const [datasetInfoError, setDatasetInfoError] = useState(null)
  const debugRef = useRef(null)
  const appendixRef = useRef(null)
  const searchRef = useRef(null)

  // Load dataset schema / row count / model label from the backend — no more guessing client-side.
  useEffect(() => {
    getDatasetInfo()
      .then(setDatasetInfo)
      .catch(err => setDatasetInfoError(err.message))
  }, [])

  // Auto-scroll debug log
  useEffect(() => {
    if (debugRef.current) debugRef.current.scrollTop = debugRef.current.scrollHeight
  }, [debugLines])

  // Animate appendix bars on scroll into view
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setChartsVisible(true) }, { threshold: 0.3 })
    if (appendixRef.current) obs.observe(appendixRef.current)
    return () => obs.disconnect()
  }, [])

  const addLog = (cls, text) => setDebugLines(prev => [...prev, { cls, text }])

  const resetRunState = () => {
    setApiResult(null)
    setApiError(null)
    setShowSpeedup(false)
    setShowResults(false)
    setStepIdx(STEPS.length - 1)
    setDebugLines([{ cls: 'dl-sys', text: 'System initialized. Awaiting parameters.' }])
  }

  const matchedIdx = INQUIRIES.findIndex(inq => inq.query === query)
  const isCustom = matchedIdx === -1

  const selectInquiry = (idx) => {
    setQuery(INQUIRIES[idx].query)
    setTaskType(INQUIRIES[idx].task_type)
    resetRunState()
  }

  const selectCustom = () => {
    setQuery('')
    setTaskType(TASK_TYPES[0].value)
    resetRunState()
    setTimeout(() => searchRef.current?.focus(), 0)
  }

  const resultsTitle = isCustom ? 'Custom Query Results' : INQUIRIES[matchedIdx].resultsTitle
  const canRun = query.trim().length > 0

  const runPipeline = async () => {
    if (isRunning || !canRun) return
    setIsRunning(true)
    setApiResult(null)
    setApiError(null)
    setShowSpeedup(false)
    setShowResults(false)
    setDebugLines([])

    // Track every step-animation timer so we can cancel the ones still pending
    // if the real response comes back early — otherwise a late timeout fires
    // AFTER we've already set the final step and drags the indicator backward.
    const stepTimers = []
    stepTimers.push(setTimeout(() => setStepIdx(1), 800))

    addLog('dl-cmd', `> Engaging LLM synthesis: ${taskType}`)
    addLog('dl-sys', '  [SYSTEM] Synthesizing code for standard CPU environment...')

    stepTimers.push(setTimeout(() => {
      setStepIdx(2)
      addLog('dl-sys', '  [SYSTEM] Synthesizing code for accelerated GPU environment...')
    }, 1600))

    stepTimers.push(setTimeout(() => {
      setStepIdx(3)
      addLog('dl-sys', '  [PROCESS] Initializing Modal sandboxes (CPU + GPU concurrently)...')
    }, 2400))

    setStepIdx(0)

    try {
      const data = await runBenchmark(query, taskType)

      stepTimers.forEach(clearTimeout)
      setStepIdx(4)
      setApiResult(data)

      const cpuS = data.cpu.execution_time_sec
      const gpuS = data.gpu.execution_time_sec
      const wallS = data.total_wall_time_sec

      if (cpuS > 0) addLog('dl-ok', `  [SUCCESS] CPU execution concluded in ${cpuS.toFixed(3)}s`)
      if (gpuS > 0) addLog('dl-ok', `  [SUCCESS] GPU execution concluded in ${gpuS.toFixed(3)}s`)

      data.gpu.logs.slice(-3).forEach(l => addLog('dl-sys', `  [GPU] ${l}`))
      data.cpu.logs.slice(-3).forEach(l => addLog('dl-sys', `  [CPU] ${l}`))

      addLog('dl-cmd', `> Total wall time: ${wallS.toFixed(1)}s`)

      if (cpuS > 0 && gpuS > 0) {
        const mult = cpuS / gpuS
        if (mult > 1) addLog('dl-ok', `  [RESULT] GPU is ${mult.toFixed(1)}x faster than CPU`)
        else addLog('dl-fix', `  [RESULT] CPU is ${(1 / mult).toFixed(1)}x faster at this scale`)
      }

      setTimeout(() => setShowResults(true), 300)
      setTimeout(() => setShowSpeedup(true), 600)

    } catch (err) {
      stepTimers.forEach(clearTimeout)
      setApiError(err.message)
      setStepIdx(STEPS.length - 1)
      addLog('dl-err', `  [FAULT] ${err.message}`)
    } finally {
      setIsRunning(false)
    }
  }

  const cpuS = apiResult?.cpu?.execution_time_sec ?? 0
  const gpuS = apiResult?.gpu?.execution_time_sec ?? 0
  const maxS = Math.max(cpuS, gpuS, 0.001)
  const cpuPct = (cpuS / maxS * 100).toFixed(1)
  const gpuPct = (gpuS / maxS * 100).toFixed(1)
  const speedupMult = cpuS > 0 && gpuS > 0 ? cpuS / gpuS : null
  const gpuWins = speedupMult && speedupMult > 1

  const liveRows = apiResult
    ? (apiResult.gpu?.results?.length > 0 ? apiResult.gpu.results : apiResult.cpu?.results ?? [])
    : []
  const summaryText = apiResult
    ? (apiResult.gpu?.results?.length > 0 ? apiResult.gpu.summary : apiResult.cpu?.summary) || ''
    : ''

  return (
    <div className="app-shell">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark">DS</span>
          <div className="brand-name">DataSense<small>GPU Console</small></div>
        </div>

        <span className="sidebar-section-label">Select Inquiry</span>
        <nav className="nav-list">
          {INQUIRIES.map((inq, i) => (
            <button
              key={inq.label}
              type="button"
              className={`nav-item${matchedIdx === i ? ' active' : ''}`}
              onClick={() => selectInquiry(i)}
            >
              <span className="nav-item-index">{String(i + 1).padStart(2, '0')}</span>
              {inq.label}
            </button>
          ))}
        </nav>

        <div className="nav-divider" />
        <button type="button" className={`nav-item nav-item-custom${isCustom ? ' active' : ''}`} onClick={selectCustom}>
          <span className="nav-item-icon">+</span> Ask Your Own
        </button>

        <div className="sidebar-footer">
          <span className="status-pill"><span className="dot" /> RAPIDS Environment Online</span>
        </div>
      </aside>

      {/* MAIN */}
      <main className="main">
        <div className="page-header">
          <div>
            <h1 className="page-title">DataSense / GPU</h1>
            <p className="page-subtitle">GPU-accelerated order intelligence — synthesize, benchmark, and compare CPU vs. GPU execution live.</p>
          </div>
          <span className="page-meta-tag">Data Architecture Console</span>
        </div>

        {/* SEARCH */}
        <div className="search-card">
          <div className="search-bar">
            <span className="search-icon"><SearchIcon /></span>
            <textarea
              ref={searchRef}
              className="search-textarea"
              rows={2}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Ask anything about the order data — e.g. “Find the 15 products with the fastest-growing sales this month.”"
            />
          </div>

          <div className="meta-row">
            <div className="meta-field">
              <span className="meta-label">Analysis Type</span>
              <select className="select-control" value={taskType} onChange={e => setTaskType(e.target.value)}>
                {TASK_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            <div className="meta-field">
              <span className="meta-label">Available Columns</span>
              <div className="columns-pill-group">
                {datasetInfo
                  ? datasetInfo.columns.map(c => (
                    <span key={c.name} className="col-pill" title={`${c.dtype} — ${c.description}`}>{c.name}</span>
                  ))
                  : <span className="col-pill col-pill-loading">{datasetInfoError ? 'Unavailable' : 'Loading…'}</span>}
              </div>
            </div>

            <div className="system-info">
              <div><b>Dataset</b>{datasetInfo ? `${datasetInfo.dataset_name} (${datasetInfo.row_count.toLocaleString()} rows)` : '—'}</div>
              <div><b>Model</b>{datasetInfo ? datasetInfo.model_name : '—'}</div>
            </div>
          </div>

          {datasetInfoError && (
            <p className="dataset-info-warning">
              Couldn't reach the backend for dataset info ({datasetInfoError}). Confirm the API is running and VITE_API_BASE_URL is set correctly.
            </p>
          )}

          <div className="execute-row">
            <button className="btn-primary" disabled={isRunning || !canRun} onClick={runPipeline}>
              {isRunning ? 'Running…' : 'Execute'}
            </button>
          </div>
        </div>

        {/* STEPPER */}
        <div className="stepper">
          {STEPS.map((step, i) => (
            <Fragment key={step}>
              <div className={`step${i === stepIdx ? ' active' : i < stepIdx ? ' done' : ''}`}>
                <span className="step-badge">{i < stepIdx ? '✓' : i + 1}</span>
                <span className="step-label">{step}</span>
              </div>
              {i < STEPS.length - 1 && <div className="step-connector" />}
            </Fragment>
          ))}
        </div>

        {/* ERROR BANNER */}
        {apiError && (
          <div className="error-banner">⚠ API error: {apiError}</div>
        )}

        {/* SYNTHESIZED LOGIC */}
        <div className="panel">
          <div className="panel-title">Synthesized Logic</div>
          <div className="split-grid">
            <div>
              <div className="code-panel-header">
                <span className="code-panel-title">CPU Implementation</span>
                <span className="code-panel-meta-group">
                  <span className="code-panel-meta">{apiResult ? `${cpuS.toFixed(3)}s` : '—'}</span>
                  {apiResult?.cpu && (
                    <ConfidenceBadge attemptsUsed={apiResult.cpu.attempts_used} confidence={apiResult.cpu.confidence} />
                  )}
                </span>
              </div>
              <div className="code-block">
                {apiResult?.cpu_code
                  ? apiResult.cpu_code
                  : <span className="cm">// Awaiting synthesis...</span>}
              </div>
            </div>
            <div>
              <div className="code-panel-header">
                <span className="code-panel-title">GPU Implementation (cuDF)</span>
                <span className="code-panel-meta-group">
                  <span className="code-panel-meta">{apiResult ? `${gpuS.toFixed(3)}s` : '—'}</span>
                  {apiResult?.gpu && (
                    <ConfidenceBadge attemptsUsed={apiResult.gpu.attempts_used} confidence={apiResult.gpu.confidence} />
                  )}
                </span>
              </div>
              <div className="code-block">
                {apiResult?.gpu_code
                  ? apiResult.gpu_code
                  : <span className="cm">// Awaiting synthesis...</span>}
              </div>
            </div>
          </div>

          <div className="debug-log" ref={debugRef}>
            {debugLines.map((line, i) => (
              <span key={i} className={`dl-line ${line.cls}`}>{line.text}</span>
            ))}
          </div>
        </div>

        {/* EXECUTION ANALYSIS */}
        <div className="panel">
          <div className="panel-title">Execution Analysis</div>
          <div className="analysis-grid">
            <div className="metrics-col">
              <div className="race-container stacked">
                <div className="race-row">
                  <div className="race-label cpu">
                    <span>Standard CPU</span>
                    <span className="race-timer">{apiResult ? `${cpuS.toFixed(3)}s` : '—'}</span>
                  </div>
                  <div className="race-track">
                    <div className="race-fill cpu-fill" style={{ width: apiResult ? `${cpuPct}%` : '0%' }} />
                  </div>
                </div>
                <div className="race-row">
                  <div className="race-label gpu">
                    <span>Accelerated GPU</span>
                    <span className="race-timer">{apiResult ? `${gpuS.toFixed(3)}s` : '—'}</span>
                  </div>
                  <div className="race-track">
                    <div className="race-fill gpu-fill" style={{ width: apiResult ? `${gpuPct}%` : '0%' }} />
                  </div>
                </div>
              </div>

              <div className={`speedup-callout${showSpeedup ? ' visible' : ''}`}>
                {speedupMult ? (
                  <>
                    <div className={`speedup-huge${!gpuWins ? ' warn' : ''}`}>
                      {gpuWins ? `${speedupMult.toFixed(1)}×` : `${(1 / speedupMult).toFixed(1)}×`}
                    </div>
                    <div className="speedup-text">
                      <h4>{gpuWins ? 'GPU Acceleration' : 'CPU Advantage'}</h4>
                      <p>
                        {gpuWins
                          ? `GPU completed ${speedupMult.toFixed(1)}× faster than CPU baseline on this query.`
                          : 'CPU proved faster at this data scale. GPU excels at higher row counts.'}
                      </p>
                    </div>
                  </>
                ) : (
                  <div className="speedup-text">
                    <h4>Performance Multiplier</h4>
                    <p>Execute a query to see real benchmark results.</p>
                  </div>
                )}
              </div>
            </div>

            <div className="results-col">
              <div className={`results-wrapper${showResults ? ' visible' : ''}`}>
                <div className="results-header">
                  <h3 className="results-title">{resultsTitle}</h3>
                  <span className="results-count">
                    {liveRows.length > 0 ? `${liveRows.length} records` : '—'}
                  </span>
                </div>
                <SummaryCard text={summaryText} />
                <ResultsTable rows={liveRows} />
              </div>
            </div>
          </div>
        </div>

        {/* APPENDIX */}
        <div className="appendix-grid" ref={appendixRef}>
          <div className="panel">
            <span className="kicker">Appendix A</span>
            <div className="panel-title">Benchmarking at Scale</div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1.5rem', maxWidth: '520px' }}>
              Empirical evaluation of cuDF versus pandas across a 20,000,000 row dataset. Execution environment: NVIDIA Tesla T4.
            </p>
            <div>
              {SWEEP_DATA.map((row) => (
                <div key={row.label} className="chart-row">
                  <div className="chart-lbl">{row.label}<small>{row.sub}</small></div>
                  <div className="chart-bar-area">
                    <div
                      className={`chart-bar${row.type === 'gpu' ? ' gpu-bar' : row.type === 'slow' ? ' slow-bar' : ''}`}
                      style={{ width: chartsVisible ? `${row.pct}%` : '0%' }}
                    />
                  </div>
                  <div className="chart-val">{row.val}×</div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <span className="kicker">Appendix B</span>
            <div className="panel-title">Key Metrics</div>
            <div className="stats-grid">
              <div className="stat-box">
                <div className="stat-val accent">
                  {speedupMult && gpuWins ? `${speedupMult.toFixed(1)}×` : '215×'}
                </div>
                <div className="stat-lbl">{speedupMult && gpuWins ? 'Live GPU Speedup' : 'Peak RF Speedup'}</div>
              </div>
              <div className="stat-box">
                <div className="stat-val">58.9×</div>
                <div className="stat-lbl">Rolling Window (20M)</div>
              </div>
              <div className="stat-box">
                <div className="stat-val muted">{apiResult ? `${cpuS.toFixed(2)}s` : '81s'}</div>
                <div className="stat-lbl">{apiResult ? 'CPU This Run' : 'CPU Baseline (RF)'}</div>
              </div>
              <div className="stat-box">
                <div className="stat-val">{apiResult ? `${gpuS.toFixed(2)}s` : '0.38s'}</div>
                <div className="stat-lbl">{apiResult ? 'GPU This Run' : 'GPU Execution (RF)'}</div>
              </div>
              <div className="stat-box">
                <div className="stat-val">1M</div>
                <div className="stat-lbl">Records Processed</div>
              </div>
              <div className="stat-box">
                <div className="stat-val">8/8</div>
                <div className="stat-lbl">Synthesis Success</div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
