import Card from '../ui/Card'

const CIRCLE_STYLES = {
  done: 'bg-[#1e3a5f] text-white',
  active: 'bg-[#e8edf2] text-[#1e3a5f] animate-pulse',
  error: 'bg-red-600 text-white',
  pending: 'bg-zinc-100 text-zinc-400',
}

const LABEL_STYLES = {
  done: 'text-zinc-900',
  active: 'text-[#1e3a5f]',
  error: 'text-red-700',
  pending: 'text-zinc-400',
}

/** stepStates: array of 'pending' | 'active' | 'done' | 'error', one per step */
function ProcessStepper({ steps = [], stepStates }) {
  const states = stepStates ?? steps.map(() => 'pending')

  return (
    <Card>
      <ol className="flex w-full flex-col gap-6 sm:flex-row sm:gap-0">
        {steps.map((step, index) => {
          const state = states[index] ?? 'pending'
          const isLast = index === steps.length - 1
          const lineDone = state === 'done' || state === 'error'

          return (
            <li key={step} className="flex items-center gap-3 sm:flex-1">
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors ${CIRCLE_STYLES[state]}`}
              >
                {state === 'error' ? '!' : index + 1}
              </span>
              <span className={`whitespace-nowrap text-sm font-medium ${LABEL_STYLES[state]}`}>
                {step}
              </span>
              {!isLast && (
                <span
                  className={`hidden h-px flex-1 sm:block ${lineDone ? 'bg-[#1e3a5f]' : 'bg-zinc-200'}`}
                />
              )}
            </li>
          )
        })}
      </ol>
    </Card>
  )
}

export default ProcessStepper
