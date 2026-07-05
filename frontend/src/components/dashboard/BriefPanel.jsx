import Card from '../ui/Card'
import Divider from '../ui/Divider'
import Pill from '../ui/Pill'
import SectionLabel from '../ui/SectionLabel'

function BriefPanel({ query, dataset, model, actionLabel = 'Execute', isRunning, onExecute }) {
  return (
    <Card>
      <SectionLabel className="mb-4">Query</SectionLabel>
      <p className="text-xl font-semibold leading-snug text-zinc-900 sm:text-2xl">{query}</p>

      <Divider className="my-6" />

      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex flex-wrap gap-2">
          <span className="rounded-lg bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-600">
            Dataset: {dataset}
          </span>
          <span className="rounded-lg bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-600">
            Model: {model}
          </span>
        </div>
        <Pill onClick={onExecute} disabled={isRunning}>
          {actionLabel}
        </Pill>
      </div>
    </Card>
  )
}

export default BriefPanel
