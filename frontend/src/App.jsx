import { useEffect, useRef, useState } from 'react'
import { analyzeQuery, analyzeQueryStream, getDatasetInfo, uploadDataset, getAvailableDatasets, loadDataset } from './api/client'
import './index.css'

const STATUS_WORDS = [
  'Accomplishing', 'Actioning', 'Actualizing', 'Baking', 'Brewing',
  'Calculating', 'Cerebrating', 'Churning', 'Clauding', 'Coalescing',
  'Cogitating', 'Computing', 'Conjuring', 'Considering', 'Cooking',
  'Crafting', 'Creating', 'Crunching', 'Deliberating', 'Determining',
  'Doing', 'Effecting', 'Finagling', 'Forging', 'Forming',
  'Generating', 'Hatching', 'Herding', 'Honking', 'Hustling',
  'Ideating', 'Inferring', 'Manifesting', 'Marinating', 'Moseying',
  'Mulling', 'Mustering', 'Musing', 'Noodling', 'Percolating',
  'Pondering', 'Processing', 'Puttering', 'Reticulating', 'Ruminating',
  'Schlepping', 'Shucking', 'Simmering', 'Smooshing', 'Spinning',
  'Stewing', 'Synthesizing', 'Thinking', 'Transmuting', 'Vibing', 'Working',
]

function randomStatusWord() {
  return STATUS_WORDS[Math.floor(Math.random() * STATUS_WORDS.length)]
}

const PRESETS = [
  {
    label: 'Revenue by Region',
    query: 'Which region has the highest total revenue and what is the revenue difference between the best and worst performing region?',
    task_type: 'data_analysis',
  },
  {
    label: 'High-Value Customers',
    query: 'Find the top 5 users by total spending. What percentage of total revenue do they represent?',
    task_type: 'data_analysis',
  },
  {
    label: 'Discount vs Revenue',
    query: 'Do transactions with above-average discounts generate more or less revenue than those with below-average discounts? Compare the average revenue and margin between the two groups.',
    task_type: 'data_analysis',
  },
  {
    label: 'Risk Profile',
    query: 'What percentage of transactions are flagged as high risk? Compare the average revenue and margin between high-risk and low-risk transactions.',
    task_type: 'data_analysis',
  },
  {
    label: 'Best Support Tier',
    query: 'Which support tier has the lowest average risk score and highest average revenue? Rank all support tiers by a combined score of revenue minus risk.',
    task_type: 'data_analysis',
  },
  {
    label: 'Full Exploration',
    query: 'Explore the dataset and provide a statistical summary of all numeric columns. Show the data types, missing value counts, and basic statistics (mean, median, min, max, std) for each numeric column.',
    task_type: 'data_analysis',
  },
  {
    label: 'Correlation Matrix',
    query: 'Compute the correlation matrix for all numeric columns. Return the top 5 most correlated pairs with their correlation coefficients.',
    task_type: 'data_analysis',
  },
]

function formatVal(v) {
  if (v === null || v === undefined) return '\u2014'
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : parseFloat(v.toFixed(4)).toString()
  return String(v)
}

function DataTable({ rows, dense }) {
  if (!rows || rows.length === 0) return (
    <p className="empty-state">No tabular output returned.</p>
  )
  const cols = Object.keys(rows[0])
  return (
    <div className="table-scroll">
      <table className={dense ? 'dense' : ''}>
        <thead>
          <tr>
            {cols.map(c => <th key={c} className="n">{c.replace(/_/g, ' ')}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 25).map((row, i) => (
            <tr key={i}>
              {cols.map(c => <td key={c} className="n">{formatVal(row[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PlatformBadge({ platform, timeSec, attempts }) {
  const tone = platform === 'gpu' ? 'gpu' : 'cpu'
  const label = platform === 'gpu' ? 'GPU' : 'CPU'
  return (
    <span className={`platform-badge ${tone}`}>
      <span className="badge-dot" />
      {label} {'\u00b7'} {timeSec.toFixed(3)}s
      {attempts ? <span className="badge-attempts">{attempts}</span> : null}
    </span>
  )
}

export default function App() {
  const [datasetInfo, setDatasetInfo] = useState(null)
  const [datasetError, setDatasetError] = useState(null)
  const [activePreset, setActivePreset] = useState(0)
  const [query, setQuery] = useState(PRESETS[0].query)
  const [taskType, setTaskType] = useState(PRESETS[0].task_type)
  const [isRunning, setIsRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [codeCollapsed, setCodeCollapsed] = useState(true)
  const [statusWord, setStatusWord] = useState('')
  const [summary, setSummary] = useState('')
  const [answer, setAnswer] = useState('')
  const [streamPhase, setStreamPhase] = useState('')
  const [currentStep, setCurrentStep] = useState(0)
  const [maxSteps, setMaxSteps] = useState(0)
  const [streamTokens, setStreamTokens] = useState('')
  const [streamCode, setStreamCode] = useState('')
  const [streamPlatform, setStreamPlatform] = useState('')
  const [retryCount, setRetryCount] = useState(0)
  const [selectedPlatform, setSelectedPlatform] = useState('auto')
  const tokenBufRef = useRef('')
  const tokenTimerRef = useRef(null)
  const [uploading, setUploading] = useState(false)
  const [availableDatasets, setAvailableDatasets] = useState([])
  const [loadingDataset, setLoadingDataset] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    getDatasetInfo()
      .then(setDatasetInfo)
      .catch(err => setDatasetError(err.message))
    getAvailableDatasets()
      .then(setAvailableDatasets)
      .catch(() => {})
  }, [])

  const switchDataset = async (key) => {
    if (!key) return
    setLoadingDataset(true)
    setError(null)
    try {
      const res = await loadDataset(key)
      const info = await getDatasetInfo()
      setDatasetInfo(info)
      setResult(null)
    } catch (err) {
      setError(`Failed to load dataset: ${err.message}`)
    } finally {
      setLoadingDataset(false)
    }
  }

  const selectPreset = (i) => {
    setActivePreset(i)
    setQuery(PRESETS[i].query)
    setTaskType(PRESETS[i].task_type)
    setResult(null)
    setError(null)
  }

  const handleCustom = () => {
    setActivePreset(-1)
    setResult(null)
    setError(null)
  }

  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadDataset(file)
      setDatasetInfo({ ...datasetInfo, row_count: res.row_count, columns: res.columns.map(c => ({ name: c, dtype: '' })) })
      setError(null)
    } catch (err) {
      setError(`Upload failed: ${err.message}`)
    } finally {
      setUploading(false)
    }
  }

  const runAnalysis = async () => {
    if (isRunning || !query.trim()) return
    setIsRunning(true)
    setResult(null)
    setError(null)
    setSummary('')
    setStatusWord(randomStatusWord())
    setAnswer('')
    setCurrentStep(0)
    setMaxSteps(0)
    setStreamPhase('')
    setStreamTokens('')
    setStreamCode('')
    setRetryCount(0)
    tokenBufRef.current = ''
    if (tokenTimerRef.current) { clearTimeout(tokenTimerRef.current); tokenTimerRef.current = null }

    try {
      await analyzeQueryStream(query, taskType, {
        onStatus: (data) => {
          setStreamPhase(data.phase)
          if (data.step) setCurrentStep(data.step)
          if (data.max_steps) setMaxSteps(data.max_steps)
          if (data.platform) setStreamPlatform(data.platform)
        },
        onToken: (token) => {
          tokenBufRef.current += token
          if (!tokenTimerRef.current) {
            const flushTokens = () => {
              const slice = tokenBufRef.current.slice(0, 5)
              if (slice) {
                setStreamTokens(prev => prev + slice)
                tokenBufRef.current = tokenBufRef.current.slice(5)
              }
              if (tokenBufRef.current.length > 0) {
                tokenTimerRef.current = setTimeout(flushTokens, 50)
              } else {
                tokenTimerRef.current = null
              }
            }
            tokenTimerRef.current = setTimeout(flushTokens, 50)
          }
        },
        onCodeReady: (data) => {
          const code = data.code
          if (tokenTimerRef.current) { clearTimeout(tokenTimerRef.current); tokenTimerRef.current = null }
          tokenBufRef.current = ''
          setStreamCode(code)
          setStreamPhase('code')
          let i = 0
          const animate = () => {
            if (i < code.length) {
              const end = Math.min(i + 3, code.length)
              setStreamTokens(code.slice(0, end))
              i = end
              if (i < code.length) {
                tokenTimerRef.current = setTimeout(animate, 40)
              } else {
                tokenTimerRef.current = null
              }
            }
          }
          tokenTimerRef.current = setTimeout(animate, 40)
        },
        onResult: (data) => {
          setResult({ results: data.results, stdout: data.stdout, stderr: data.stderr, success: data.success, step: data.step, code: streamCode })
          if (data.success) setStreamPhase('result')
        },
        onAnswer: (text) => {
          setAnswer(text)
          setStreamPhase('answer')
        },
        onSummary: (text) => {
          setSummary(text)
        },
        onRetry: (data) => {
          setRetryCount(data.attempt)
          setStreamPhase('executing')
        },
        onLog: (msg) => {
          // could display in a log panel
        },
        onError: (msg) => {
          setError(msg)
          setStreamPhase('error')
        },
        onDone: () => {
          if (tokenBufRef.current) {
            setStreamTokens(prev => prev + tokenBufRef.current)
            tokenBufRef.current = ''
          }
          setIsRunning(false)
          setStreamPhase(prev => prev === 'done' ? 'done' : 'done')
        },
      }, selectedPlatform)
    } catch (err) {
      setError(err.message)
      setStreamPhase('error')
    } finally {
      setIsRunning(false)
    }
  }

  const previewRows = datasetInfo?.preview ?? []
  const resultRows = result?.results ?? []
  const platform = result?.platform ?? ''
  const execTime = result?.execution_time_sec ?? 0
  const warmupTime = result?.warmup_time_sec ?? 0

  return (
    <div className="container">
      <header className="masthead">
        <h1>DataSense</h1>
        <div className="masthead-meta">
          <span>Data Analysis Platform</span>
          <span className="status-indicator">
            <span className="status-dot" />
            {datasetInfo ? `${datasetInfo.row_count.toLocaleString()} rows` : 'Loading...'}
          </span>
          <span>v2.0</span>
        </div>
      </header>

      <section className="dataset-section">
        <div className="dataset-header">
          <span className="section-kicker">Working Dataset</span>
          <div className="dataset-controls">
            <select
              className="dataset-select"
              onChange={e => switchDataset(e.target.value)}
              defaultValue=""
              disabled={loadingDataset}
            >
              <option value="" disabled>Switch dataset{'\u2026'}</option>
              {availableDatasets.map(ds => (
                <option key={ds.key} value={ds.key}>
                  {ds.label}{ds.cached ? '' : ' \u2601'}
                </option>
              ))}
            </select>
            <button
              className="btn-outline upload-btn"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? 'Uploading...' : '\u2B06 Upload CSV'}
            </button>
            <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} hidden />
          </div>
        </div>
        <div key={datasetInfo?.source ?? 'empty'} className={`dataset-card${loadingDataset ? ' refreshing' : ' refreshed'}`}>
          <div className="dataset-card-body">
            {loadingDataset ? (
              <div className="dataset-refresh-pulse">
                <span className="refresh-line" />
                <span className="refresh-line" />
                <span className="refresh-line" />
                <span className="refresh-line" />
              </div>
            ) : (
              <>
                <div className="dataset-meta">
                  {datasetInfo ? (
                    <>
                      <span className="dataset-stat">
                        <span className="stat-value">{datasetInfo.row_count.toLocaleString()}</span>
                        <span className="stat-label">rows</span>
                      </span>
                      <span className="dim-bullet" />
                      <span className="dataset-stat">
                        <span className="stat-value">{datasetInfo.column_count}</span>
                        <span className="stat-label">columns</span>
                      </span>
                      <span className="dim-bullet" />
                      <span className="dataset-source">{datasetInfo.source}</span>
                    </>
                  ) : datasetError ? (
                    <span className="dataset-error">Dataset unavailable: {datasetError}</span>
                  ) : (
                    <span className="dataset-loading">Loading{'\u2026'}</span>
                  )}
                </div>
                {previewRows.length > 0 && (
                  <div className="preview-table">
                    <DataTable rows={previewRows} dense />
                  </div>
                )}
              </>
            )}
          </div>
        </div>
        {error && !isRunning && <div className="flash-error">{error}</div>}
      </section>

      <hr className="separator" />

      <section className="brief-section">
        <span className="section-kicker">The Brief</span>
        <div className="query-area">
          <textarea
            className="query-input"
            rows={3}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={handleCustom}
            placeholder="Describe the analysis you want to perform..."
          />
        </div>
        <div className="preset-row">
          {PRESETS.map((p, i) => (
            <button
              key={i}
              className={`preset-btn${i === activePreset ? ' active' : ''}`}
              onClick={() => selectPreset(i)}
            >
              {p.label}
            </button>
          ))}
          <button
            className={`preset-btn${activePreset === -1 ? ' active' : ''}`}
            onClick={handleCustom}
          >
            + Custom
          </button>
        </div>
        <div className="action-row">
          <span className="action-hint">
            <select className="platform-select" value={selectedPlatform} onChange={e => setSelectedPlatform(e.target.value)} disabled={isRunning}>
              <option value="auto">Auto-detect platform</option>
              <option value="cpu">CPU (pandas/sklearn)</option>
              <option value="gpu">GPU (cuDF/cuML)</option>
            </select>
          </span>
          <button className="run-btn" disabled={isRunning || !query.trim()} onClick={runAnalysis}>
            {isRunning ? 'Running\u2026' : '\u25B6 Execute Analysis'}
          </button>
        </div>
      </section>

      <hr className="separator" />

      <section className="results-section">
        {error && (
          <div className="error-banner">{error}</div>
        )}

        {(isRunning || streamPhase) && (
          <div className="stream-panel">
            <div className="stream-phase">
              <span className={`phase-dot ${streamPhase}`} />
              {streamPhase === 'routing' && 'Starting agent...'}
              {streamPhase === 'reasoning' && currentStep > 0 && `Step ${currentStep}/${maxSteps}`}
              {streamPhase === 'code' && `Code generated (step ${result?.step || currentStep})`}
              {streamPhase === 'executing' && `Executing step ${currentStep}...`}
              {streamPhase === 'result' && `Step ${result?.step || currentStep} complete`}
              {streamPhase === 'answer' && 'Answer found'}
              {streamPhase === 'error' && 'Error'}
              {streamPhase === '' && 'Starting...'}
              {streamPhase === 'done' && 'Done'}
            </div>
            {currentStep > 0 && (
              <div className="step-track">
                {Array.from({length: maxSteps || 8}, (_, i) => (
                  <span key={i} className={`step-dot${i < currentStep ? ' done' : ''}${i === currentStep - 1 ? ' active' : ''}${i === (result?.step || currentStep) - 1 && streamPhase === 'executing' ? ' running' : ''}`} />
                ))}
              </div>
            )}
            {streamTokens && streamPhase === 'code' && (
              <div className="generated-code">
                <div className="code-header" style={{cursor: 'pointer'}}>
                  <span>Generated Code</span>
                  <span className="code-lang">Python</span>
                </div>
                <pre className={`stream-code streaming`}>{streamTokens}</pre>
              </div>
            )}
          </div>
        )}

        {(isRunning || answer) && (
          <div className="answer-card">
            <span className="answer-label">Result</span>
            <p className="answer-text">{summary || (statusWord ? `${statusWord}...` : '')}</p>
          </div>
        )}

        {(result || answer) && (
          <>
            {result && result.results && result.results.length > 0 && (
              <>
                <div className="results-header">
                  <h2 className="section-title">Results</h2>
                  <div className="result-meta">
                    {result.success === false && <span className="warmup-note" style={{color: 'var(--alert)'}}>Execution error</span>}
                    {result.stderr && <span className="warmup-note" style={{color: 'var(--alert)'}}>{result.stderr.slice(0, 100)}</span>}
                  </div>
                </div>
                <DataTable rows={resultRows} />
              </>
            )}

            {streamTokens && streamPhase !== 'code' && (
              <div className="generated-code">
                <div className="code-header" onClick={() => setCodeCollapsed(!codeCollapsed)} style={{cursor: 'pointer'}}>
                  <span>Generated Code</span>
                  <span className="code-lang">Python</span>
                  <span className="collapse-icon">{codeCollapsed ? '\u25B8' : '\u25BE'}</span>
                </div>
                {!codeCollapsed && (
                  <pre className="code-block">{streamTokens}</pre>
                )}
              </div>
            )}
          </>
        )}

        {!result && !error && !isRunning && (
          <p className="empty-state">Select a preset or type a custom query and execute.</p>
        )}
      </section>
    </div>
  )
}
