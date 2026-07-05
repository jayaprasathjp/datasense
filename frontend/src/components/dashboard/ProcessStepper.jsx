import Card from '../ui/Card'

function ProcessStepper({ steps = [], activeIndex }) {
  return (
    <Card>
      <ol className="flex w-full flex-col gap-6 sm:flex-row sm:gap-0">
        {steps.map((step, index) => {
          const isDone = activeIndex !== undefined && index < activeIndex
          const isCurrent = index === activeIndex
          const isComplete = isDone || isCurrent
          const isLast = index === steps.length - 1

          return (
            <li key={step} className="flex items-center gap-3 sm:flex-1">
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors ${
                  isComplete ? 'bg-indigo-600 text-white' : 'bg-zinc-100 text-zinc-400'
                }`}
              >
                {index + 1}
              </span>
              <span
                className={`whitespace-nowrap text-sm font-medium ${
                  isComplete ? 'text-zinc-900' : 'text-zinc-400'
                }`}
              >
                {step}
              </span>
              {!isLast && (
                <span
                  className={`hidden h-px flex-1 sm:block ${
                    isDone ? 'bg-indigo-600' : 'bg-zinc-200'
                  }`}
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
