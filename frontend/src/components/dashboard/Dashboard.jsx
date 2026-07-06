import { useEffect, useRef, useState } from 'react'
import Masthead from './Masthead'
import InquirySidebar from './InquirySidebar'
import BriefPanel from './BriefPanel'
import ProcessStepper from './ProcessStepper'
import SynthesizedLogic from './SynthesizedLogic'
import InquiryResults from './inquiries/InquiryResults'
import BenchmarkStrip from './BenchmarkStrip'
import Card from '../ui/Card'
import SectionLabel from '../ui/SectionLabel'

const INQUIRIES = [
  {
    label: 'Risk Classification (RF)',
    query:
      'Train a classifier to predict risk_label from numeric columns (feat_1 to feat_4, price, qty, discount_pct, ticket_age_hours, sentiment, days_since_restock). Return the top 20 highest-risk rows with predicted probability as a new column called pred_risk.',
    task_type: 'Risk scoring / classification',
  },
  {
    label: 'Time-Series Alerting',
    query:
      "Compute a 7-day rolling average revenue per store. Flag the top 10 stores where today's revenue is more than 20% below the rolling average. Return a dataframe of those anomalies.",
    task_type: 'Time-series alerting',
  },
  {
    label: 'Operational Triage',
    query:
      'Rank the top 25 rows by operational priority using return_flag, ticket_age_hours, days_since_restock, sentiment, and margin. Add a priority_score column and return the ranked dataframe.',
    task_type: 'data_analysis',
  },
  {
    label: 'Executive Summary',
    query:
      'Create an aggregated dashboard summary grouped by region and support_tier. Show total revenue, average margin, return rate, average ticket_age_hours, and average sentiment.',
    task_type: 'data_analysis',
  },
]

const STEPS = ['Acquisition', 'Synthesis (LLM)', 'CPU Baseline', 'GPU Acceleration', 'Resolution']

function CodeBlock({ code }) {
  return (
    <pre className="whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-zinc-700">
      {code}
    </pre>
  )
}

function Dashboard({
  title = 'DataSense / GPU',
  dataset = 'Synthetic transactions (1M rows)',
  model = 'Gemma-4-E2B (LoRA) via Modal',
}) {
  const [activeInquiry, setActiveInquiry] = useState(0)
  const [stepIndex, setStepIndex] = useState(STEPS.length - 1)
  const [isRunning, setIsRunning] = useState(false)
  const [apiResult, setApiResult] = useState(null)   // real API response
  const [apiError, setApiError] = useState(null)
  const stepTimerRef = useRef(null)

  useEffect(() => {
    // Reset result when switching inquiry so mock view shows
    setApiResult(null)
    setApiError(null)
    setStepIndex(STEPS.length - 1)
  }, [activeInquiry])

  useEffect(() => () => clearInterval(stepTimerRef.current), [])

  const animateSteps = (onDone) => {
    clearInterval(stepTimerRef.current)
    let step = 0
    setStepIndex(0)
    stepTimerRef.current = setInterval(() => {
      step += 1
      if (step >= STEPS.length - 1) {
        clearInterval(stepTimerRef.current)
        setStepIndex(STEPS.length - 1)
        onDone()
      } else {
        setStepIndex(step)
      }
    }, 600)
  }

  const runPipeline = async () => {
    if (isRunning) return
    setIsRunning(true)
    setApiResult(null)
    setApiError(null)

    const inquiry = INQUIRIES[activeInquiry]

    // Start step animation concurrently with the API call
    // The animation will run ahead and pause at "GPU Acceleration"
    setStepIndex(1) // Synthesis (LLM)

    try {
      const res = await fetch('/api/benchmark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: inquiry.query, task_type: inquiry.task_type }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      setStepIndex(STEPS.length - 1) // Resolution
      setApiResult(data)
    } catch (err) {
      setApiError(err.message)
      setStepIndex(STEPS.length - 1)
    } finally {
      setIsRunning(false)
    }
  }

  const inquiry = INQUIRIES[activeInquiry]

  return (
    <div className="mx-auto min-h-screen w-full max-w-6xl px-6 sm:px-10">
      <Masthead title={title} />

      <div className="flex flex-col gap-6 pb-16">
        <div className="flex flex-col gap-6 sm:flex-row">
          <div className="w-full sm:w-64 sm:shrink-0">
            <InquirySidebar
              items={INQUIRIES.map((i) => i.label)}
              activeIndex={activeInquiry}
              onSelect={setActiveInquiry}
            />
          </div>

          <div className="min-w-0 flex-1">
            <BriefPanel
              query={inquiry.query}
              dataset={dataset}
              model={model}
              actionLabel={isRunning ? 'Running… (may take 3-5 min)' : 'Execute'}
              isRunning={isRunning}
              onExecute={runPipeline}
            />
          </div>
        </div>

        <ProcessStepper steps={STEPS} activeIndex={stepIndex} />

        {/* Error banner */}
        {apiError && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-3 text-sm text-red-700">
            ⚠ API error: {apiError}
          </div>
        )}

        {/* Benchmark timing strip — only after real API result */}
        {apiResult && (
          <BenchmarkStrip
            cpuSeconds={apiResult.cpu.execution_time_sec}
            gpuSeconds={apiResult.gpu.execution_time_sec}
            note={`Wall time: ${apiResult.total_wall_time_sec.toFixed(1)}s`}
          />
        )}

        <Card>
          <SectionLabel className="mb-6">Output</SectionLabel>
          <InquiryResults activeIndex={activeInquiry} apiResult={apiResult} />
        </Card>

        <SynthesizedLogic
          figures={[
            {
              label: 'CPU Implementation (pandas + sklearn)',
              content: (
                <CodeBlock
                  code={apiResult?.cpu_code || '// Run a query to see the synthesized pandas code'}
                />
              ),
            },
            {
              label: 'GPU Implementation (cuDF + cuML)',
              content: (
                <CodeBlock
                  code={apiResult?.gpu_code || '// Run a query to see the synthesized cuDF code'}
                />
              ),
            },
          ]}
        />
      </div>
    </div>
  )
}

export default Dashboard
