import { useEffect, useRef, useState } from 'react'
import Masthead from './Masthead'
import InquirySidebar from './InquirySidebar'
import BriefPanel from './BriefPanel'
import ProcessStepper from './ProcessStepper'
import SynthesizedLogic from './SynthesizedLogic'
import InquiryResults from './inquiries/InquiryResults'
import Card from '../ui/Card'
import SectionLabel from '../ui/SectionLabel'
import { CODE_SNIPPETS } from '../../data/mockData'

const INQUIRIES = [
  {
    label: 'Risk Classification (RF)',
    query:
      'Train a classifier to predict delay_risk_label from numeric features and return the top 20 highest-risk shipments with pred_risk probability.',
    codeKey: 'riskClassification',
  },
  {
    label: 'Time-Series Alerting',
    query:
      "Compute a 7-day rolling average parcel volume per distribution hub. Flag the top 10 hubs where today's volume is more than 30% above the rolling average.",
    codeKey: 'timeSeriesAlerting',
  },
  {
    label: 'Operational Triage',
    query:
      'Rank the top 25 shipments by operational priority using vehicle_breakdown_flag, ticket_age_hours, weather_severity, sentiment, and delay_cost.',
    codeKey: 'operationalTriage',
  },
  {
    label: 'Executive Summary',
    query:
      'Create a dashboard summary grouped by region and hub_tier showing total shipments, on-time rate, avg delay, vehicle breakdown rate, and avg sentiment.',
    codeKey: 'executiveSummary',
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
  title = 'FleetPulse / GPU',
  dataset = 'global_logistics_network (181K shipments)',
  model = 'Gemma-4-E2B (LoRA)',
}) {
  const [activeInquiry, setActiveInquiry] = useState(0)
  const [stepIndex, setStepIndex] = useState(STEPS.length - 1)
  const [isRunning, setIsRunning] = useState(false)
  const intervalRef = useRef(null)

  useEffect(() => () => clearInterval(intervalRef.current), [])

  const runPipeline = () => {
    clearInterval(intervalRef.current)
    setIsRunning(true)
    let step = 0
    setStepIndex(0)
    intervalRef.current = setInterval(() => {
      step += 1
      if (step >= STEPS.length) {
        clearInterval(intervalRef.current)
        setIsRunning(false)
        setStepIndex(STEPS.length - 1)
      } else {
        setStepIndex(step)
      }
    }, 320)
  }

  const inquiry = INQUIRIES[activeInquiry]
  const codeSnippet = CODE_SNIPPETS[inquiry.codeKey]

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
              actionLabel={isRunning ? 'Running…' : 'Execute'}
              isRunning={isRunning}
              onExecute={runPipeline}
            />
          </div>
        </div>

        <ProcessStepper steps={STEPS} activeIndex={stepIndex} />

        <Card>
          <SectionLabel className="mb-6">Output</SectionLabel>
          <InquiryResults activeIndex={activeInquiry} />
        </Card>

        <SynthesizedLogic
          figures={[
            { label: 'CPU Implementation', content: <CodeBlock code={codeSnippet.cpu} /> },
            { label: 'GPU Implementation (cuDF)', content: <CodeBlock code={codeSnippet.gpu} /> },
          ]}
        />
      </div>
    </div>
  )
}

export default Dashboard
