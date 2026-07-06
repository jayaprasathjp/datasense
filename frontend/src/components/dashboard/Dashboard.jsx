import { useState } from 'react'
import Masthead from './Masthead'
import InquirySidebar from './InquirySidebar'
import BriefPanel from './BriefPanel'
import ProcessStepper from './ProcessStepper'
import SynthesizedLogic from './SynthesizedLogic'
import InquiryOutput from './InquiryOutput'
import Card from '../ui/Card'
import SectionLabel from '../ui/SectionLabel'
import { INQUIRIES } from '../../data/inquiries'
import { synthesizeCode, executeCpu, executeGpu } from '../../api/client'

const STEPS = ['Acquisition', 'Synthesis (LLM)', 'CPU Baseline', 'GPU Acceleration', 'Resolution']

const emptyRun = () => ({
  stepStates: STEPS.map(() => 'pending'),
  cpuCode: null,
  gpuCode: null,
  cpu: null,
  gpu: null,
  synthesisError: null,
})

function setAt(arr, index, value) {
  const next = [...arr]
  next[index] = value
  return next
}

function CodeBlock({ code }) {
  return (
    <pre className="whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-zinc-700">
      {code}
    </pre>
  )
}

function Dashboard({
  title = 'FleetPulse / GPU',
  dataset = 'thelook_ecommerce.order_items (BigQuery)',
  model = 'Gemma-4-E2B (LoRA) via Modal',
}) {
  const [activeInquiry, setActiveInquiry] = useState(0)
  const [runs, setRuns] = useState({})

  const currentRun = runs[activeInquiry] ?? emptyRun()
  const isRunning = currentRun.stepStates.includes('active')

  const updateRun = (index, updater) => {
    setRuns((prev) => ({ ...prev, [index]: updater(prev[index] ?? emptyRun()) }))
  }

  const runPipeline = async () => {
    const index = activeInquiry
    const inquiry = INQUIRIES[index]

    updateRun(index, () => ({
      ...emptyRun(),
      stepStates: setAt(setAt(STEPS.map(() => 'pending'), 0, 'done'), 1, 'active'),
    }))

    let cpuCode
    let gpuCode
    try {
      const synthesis = await synthesizeCode(inquiry.query, inquiry.taskType)
      cpuCode = synthesis.cpu_code
      gpuCode = synthesis.gpu_code
      updateRun(index, (prev) => ({
        ...prev,
        cpuCode,
        gpuCode,
        stepStates: setAt(setAt(setAt(prev.stepStates, 1, 'done'), 2, 'active'), 3, 'active'),
      }))
    } catch (err) {
      updateRun(index, (prev) => ({
        ...prev,
        synthesisError: err.message,
        stepStates: setAt(prev.stepStates, 1, 'error'),
      }))
      return
    }

    const cpuPromise = executeCpu(cpuCode)
      .then((res) => {
        const cpuState =
          res.status === 'success'
            ? { status: 'done', seconds: res.execution_time_sec, results: res.results }
            : { status: 'error', seconds: res.execution_time_sec, error: res.status }
        updateRun(index, (prev) => ({
          ...prev,
          cpu: cpuState,
          stepStates: setAt(prev.stepStates, 2, cpuState.status),
        }))
      })
      .catch((err) => {
        updateRun(index, (prev) => ({
          ...prev,
          cpu: { status: 'error', error: err.message },
          stepStates: setAt(prev.stepStates, 2, 'error'),
        }))
      })

    const gpuPromise = executeGpu(gpuCode)
      .then((res) => {
        const gpuState = {
          status: 'done',
          seconds: res.execution_time_sec,
          results: res.results,
          logs: res.logs,
        }
        updateRun(index, (prev) => ({
          ...prev,
          gpu: gpuState,
          stepStates: setAt(prev.stepStates, 3, 'done'),
        }))
      })
      .catch((err) => {
        updateRun(index, (prev) => ({
          ...prev,
          gpu: { status: 'error', error: err.message },
          stepStates: setAt(prev.stepStates, 3, 'error'),
        }))
      })

    await Promise.allSettled([cpuPromise, gpuPromise])
    updateRun(index, (prev) => ({ ...prev, stepStates: setAt(prev.stepStates, 4, 'done') }))
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
              actionLabel={isRunning ? 'Running…' : 'Execute'}
              isRunning={isRunning}
              onExecute={runPipeline}
            />
          </div>
        </div>

        <ProcessStepper steps={STEPS} stepStates={currentRun.stepStates} />

        <Card>
          <SectionLabel className="mb-6">Output</SectionLabel>
          <InquiryOutput cpu={currentRun.cpu} gpu={currentRun.gpu} />
        </Card>

        {(currentRun.cpuCode || currentRun.gpuCode) && (
          <SynthesizedLogic
            figures={[
              { label: 'CPU Implementation', content: <CodeBlock code={currentRun.cpuCode} /> },
              { label: 'GPU Implementation (cuDF)', content: <CodeBlock code={currentRun.gpuCode} /> },
            ]}
          />
        )}
      </div>
    </div>
  )
}

export default Dashboard
