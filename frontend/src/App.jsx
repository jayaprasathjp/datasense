import { useEffect, useRef, useState } from 'react'
import './index.css'

const INQUIRIES = [
  {
    label: 'I. Risk Classification (RF)',
    query: 'Train a classifier to predict risk_label from numeric columns (feat_1 to feat_4, price, qty, discount_pct, ticket_age_hours, sentiment, days_since_restock). Return the top 20 highest-risk rows with predicted probability as a new column called pred_risk.',
    task_type: 'Risk scoring / classification',
    resultsTitle: 'Risk Classification Output',
  },
  {
    label: 'II. Time-Series Alerting',
    query: "Compute a 7-day rolling average revenue per store. Flag the top 10 stores where today's revenue is more than 20% below the rolling average. Return a dataframe of those anomalies.",
    task_type: 'Time-series alerting',
    resultsTitle: 'Anomalous Revenue Deterioration',
  },
  {
    label: 'III. Operational Triage',
    query: 'Rank the top 25 rows by operational priority using return_flag, ticket_age_hours, days_since_restock, sentiment, and margin. Add a priority_score column and return the ranked dataframe.',
    task_type: 'data_analysis',
    resultsTitle: 'Operational Triage Matrix',
  },
  {
    label: 'IV. Executive Summary',
    query: 'Create an aggregated dashboard summary grouped by region and support_tier. Show total revenue, average margin, return rate, average ticket_age_hours, and average sentiment.',
    task_type: 'data_analysis',
    resultsTitle: 'Cross-Regional Performance Extract',
  },
]

const STEPS = ['Acquisition', 'Synthesis (LLM)', 'CPU Baseline', 'GPU Acceleration', 'Resolution']
const ROMAN = ['I', 'II', 'III', 'IV', 'V']

// Kaggle sweep results (static reference data from notebook Section D)
const SWEEP_DATA = [
  { label: 'Time-series alerting', sub: 'rolling_window', val: 58.9, pct: 100, type: 'gpu' },
  { label: 'Dashboard enrichment', sub: 'merge_join',     val: 39.8, pct: 67,  type: 'gpu' },
  { label: 'Priority ranking',     sub: 'sort_values',    val: 21.1, pct: 36,  type: 'ink' },
  { label: 'BI aggregation',       sub: 'groupby_agg',    val: 18.4, pct: 31,  type: 'ink' },
  { label: 'Risk modeling (5M)',   sub: 'rf_classify_fit', val: 15.7, pct: 27, type: 'ink' },
  { label: 'Forecasting',          sub: 'linreg_fit',     val: 11.7, pct: 20,  type: 'ink' },
  { label: 'Segmentation (weak)',  sub: 'kmeans_fit',     val: 3.0,  pct: 5,   type: 'slow' },
]

function formatVal(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'number') return Number.isInteger(val) ? val.toLocaleString() : parseFloat(val.toFixed(4)).toString()
  return String(val)
}

function ResultsTable({ rows, title, count }) {
  if (!rows || rows.length === 0) return (
    <p style={{ fontFamily: 'var(--sans)', fontSize: '0.85rem', color: 'var(--ink-lighter)', fontStyle: 'italic' }}>
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
              <th key={col} className="n">{col.replace(/_/g, ' ')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 25).map((row, i) => (
            <tr key={i}>
              {columns.map(col => (
                <td key={col} className="n">{formatVal(row[col])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function App() {
  const [activeIdx, setActiveIdx]     = useState(0)
  const [query, setQuery]             = useState(INQUIRIES[0].query)
  const [stepIdx, setStepIdx]         = useState(STEPS.length - 1)
  const [isRunning, setIsRunning]     = useState(false)
  const [apiResult, setApiResult]     = useState(null)
  const [apiError, setApiError]       = useState(null)
  const [debugLines, setDebugLines]   = useState([{ cls: 'dl-sys', text: 'System initialized. Awaiting parameters.' }])
  const [showSpeedup, setShowSpeedup] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const [chartsVisible, setChartsVisible] = useState(false)
  const debugRef = useRef(null)
  const appendixRef = useRef(null)

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

  const selectInquiry = (idx) => {
    setActiveIdx(idx)
    setQuery(INQUIRIES[idx].query)
    setApiResult(null)
    setApiError(null)
    setShowSpeedup(false)
    setShowResults(false)
    setStepIdx(STEPS.length - 1)
    setDebugLines([{ cls: 'dl-sys', text: 'System initialized. Awaiting parameters.' }])
  }

  const runPipeline = async () => {
    if (isRunning) return
    const inquiry = INQUIRIES[activeIdx]
    setIsRunning(true)
    setApiResult(null)
    setApiError(null)
    setShowSpeedup(false)
    setShowResults(false)
    setDebugLines([])

    // Step through pipeline visually
    const stepDelay = (i) => new Promise(r => setTimeout(r, i * 800))
    setStepIdx(0)
    setTimeout(() => setStepIdx(1), 800)

    addLog('dl-cmd', `> Engaging LLM synthesis: ${inquiry.task_type}`)
    addLog('dl-sys', '  [SYSTEM] Synthesizing code for standard CPU environment...')

    setTimeout(() => {
      setStepIdx(2)
      addLog('dl-sys', '  [SYSTEM] Synthesizing code for accelerated GPU environment...')
    }, 1600)

    setTimeout(() => {
      setStepIdx(3)
      addLog('dl-sys', '  [PROCESS] Initializing Modal sandboxes (CPU + GPU concurrently)...')
    }, 2400)

    try {
      const res = await fetch('/api/benchmark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: inquiry.query, task_type: inquiry.task_type }),
      })
      if (!res.ok) {
        let errMsg = `HTTP ${res.status}`
        try {
          const err = await res.json()
          errMsg = err.detail || errMsg
        } catch { /* response body wasn't JSON */ }
        throw new Error(errMsg)
      }
      const data = await res.json()

      setStepIdx(4)
      setApiResult(data)

      // Log results
      const cpuS = data.cpu.execution_time_sec
      const gpuS = data.gpu.execution_time_sec
      const wallS = data.total_wall_time_sec

      if (cpuS > 0) addLog('dl-ok', `  [SUCCESS] CPU execution concluded in ${cpuS.toFixed(3)}s`)
      if (gpuS > 0) addLog('dl-ok', `  [SUCCESS] GPU execution concluded in ${gpuS.toFixed(3)}s`)

      // Log sandbox notes
      data.gpu.logs.slice(-3).forEach(l => addLog('dl-sys', `  [GPU] ${l}`))
      data.cpu.logs.slice(-3).forEach(l => addLog('dl-sys', `  [CPU] ${l}`))

      addLog('dl-cmd', `> Total wall time: ${wallS.toFixed(1)}s`)

      if (cpuS > 0 && gpuS > 0) {
        const mult = cpuS / gpuS
        if (mult > 1) addLog('dl-ok', `  [RESULT] GPU is ${mult.toFixed(1)}x faster than CPU`)
        else addLog('dl-fix', `  [RESULT] CPU is ${(1/mult).toFixed(1)}x faster at this scale`)
      }

      setTimeout(() => setShowResults(true), 300)
      setTimeout(() => setShowSpeedup(true), 600)

    } catch (err) {
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

  const inquiry = INQUIRIES[activeIdx]

  return (
    <div className="container">
      {/* MASTHEAD */}
      <header className="masthead">
        <h1>DataSense / GPU</h1>
        <div className="masthead-meta">
          <span>Vol. 26 — No. 07</span>
          <div className="status-indicator">
            <span className="status-dot" />
            RAPIDS Environment Online
          </div>
          <span>Data Architecture Review</span>
        </div>
      </header>

      {/* THE BRIEF */}
      <section className="brief-section">
        <aside className="query-sidebar">
          <span className="section-kicker">Select Inquiry</span>
          <div className="query-pills">
            {INQUIRIES.map((inq, i) => (
              <button key={i} className={`qpill${i === activeIdx ? ' active' : ''}`} onClick={() => selectInquiry(i)}>
                {inq.label}
              </button>
            ))}
          </div>
        </aside>

        <main className="query-main">
          <span className="section-kicker">The Brief</span>
          <div className="query-input-wrapper">
            <textarea
              className="query-input"
              rows={3}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Formulate your inquiry..."
            />
          </div>
          <div className="run-action">
            <div className="run-meta">
              Dataset: Synthetic transactions (1M rows)<br />
              Model: Gemma-4-E2B (LoRA) via Modal
            </div>
            <button className="run-btn" disabled={isRunning} onClick={runPipeline}>
              {isRunning ? 'Running…' : 'Execute'}
            </button>
          </div>
        </main>
      </section>

      {/* PIPELINE */}
      <div className="pipeline">
        {STEPS.map((step, i) => (
          <div key={i} className={`pipe-step${i === stepIdx ? ' active' : i < stepIdx ? ' done' : ''}`}>
            <span className="pipe-num">{ROMAN[i]}</span>
            <span className="pipe-label">{step}</span>
          </div>
        ))}
      </div>

      {/* ERROR BANNER */}
      {apiError && (
        <div className="error-banner">⚠ API Error: {apiError}</div>
      )}

      {/* SYNTHESIZED LOGIC */}
      <div className="logic-section">
        <h2 className="section-title">Synthesized Logic</h2>
        <div className="logic-grid">
          <div className="figure">
            <div className="figure-caption">
              <span>Figure A: CPU Implementation</span>
              <span className="caption-meta">{apiResult ? `${cpuS.toFixed(3)}s execution` : '—'}</span>
            </div>
            <div className="code-block">
              {apiResult?.cpu_code
                ? apiResult.cpu_code
                : <span className="cm">// Awaiting synthesis...</span>
              }
            </div>
          </div>
          <div className="figure">
            <div className="figure-caption">
              <span>Figure B: GPU Implementation (cuDF)</span>
              <span className="caption-meta">{apiResult ? `${gpuS.toFixed(3)}s execution` : '—'}</span>
            </div>
            <div className="code-block">
              {apiResult?.gpu_code
                ? apiResult.gpu_code
                : <span className="cm">// Awaiting synthesis...</span>
              }
            </div>
          </div>
        </div>

        {/* DEBUG LOG */}
        <div className="debug-log-wrapper" ref={debugRef}>
          {debugLines.map((line, i) => (
            <span key={i} className={`dl-line ${line.cls}`}>{line.text}</span>
          ))}
        </div>
      </div>

      <hr className="separator" />

      {/* EXECUTION ANALYSIS */}
      <div className="execution-section">
        <h2 className="section-title">Execution Analysis</h2>
        <div className="analysis-grid">
          {/* Race bars */}
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
                    {gpuWins ? `${speedupMult.toFixed(1)}×` : `${(1/speedupMult).toFixed(1)}×`}
                  </div>
                  <div className="speedup-text">
                    <h4>{gpuWins ? 'GPU Acceleration' : 'CPU Advantage'}</h4>
                    <p>
                      {gpuWins
                        ? `GPU completed ${speedupMult.toFixed(1)}× faster than CPU baseline on this query.`
                        : `CPU proved faster at this data scale. GPU excels at higher row counts.`
                      }
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

          {/* Results table */}
          <div className="results-col">
            <div className={`results-wrapper${showResults ? ' visible' : ''}`}>
              <div className="results-header">
                <h3 className="results-title">{inquiry.resultsTitle}</h3>
                <span className="results-count">
                  {liveRows.length > 0 ? `${liveRows.length} records` : '—'}
                </span>
              </div>
              <ResultsTable rows={liveRows} />
            </div>
          </div>
        </div>
      </div>

      <hr className="separator" />

      {/* APPENDIX */}
      <div className="appendix-grid" ref={appendixRef}>
        <div>
          <span className="section-kicker">Appendix A</span>
          <h2 className="section-title" style={{ fontSize: '2rem' }}>Benchmarking at Scale</h2>
          <p style={{ fontFamily: 'var(--sans)', fontSize: '0.8rem', color: 'var(--ink-light)', marginBottom: '2rem', maxWidth: '600px' }}>
            Empirical evaluation of cuDF versus pandas across a 20,000,000 row dataset. Execution environment: NVIDIA Tesla T4.
          </p>
          <div className="chart-container">
            {SWEEP_DATA.map((row, i) => (
              <div key={i} className="chart-row">
                <div className="chart-lbl">{row.label}<small>{row.sub}</small></div>
                <div className="chart-bar-area">
                  <div
                    className={`chart-bar${row.type === 'gpu' ? ' gpu-bar' : row.type === 'slow' ? ' slow-bar' : ''}`}
                    style={{ width: chartsVisible ? `${row.pct}%` : '0%' }}
                  />
                </div>
                <div
                  className="chart-val"
                  style={{ color: row.type === 'gpu' ? 'var(--gpu-accent)' : row.type === 'slow' ? 'var(--alert)' : 'inherit' }}
                >
                  {row.val}×
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <span className="section-kicker">Appendix B</span>
          <h2 className="section-title" style={{ fontSize: '2rem' }}>Key Metrics</h2>
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
    </div>
  )
}
