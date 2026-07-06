import Card from '../ui/Card'

function Figure({ label, children }) {
  return (
    <div className="flex-1">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        {label}
      </p>
      <div className="overflow-x-auto rounded-xl bg-zinc-50 p-4">{children}</div>
    </div>
  )
}

function SynthesizedLogic({ heading = 'Synthesized Logic', figures = [], className = '' }) {
  return (
    <Card className={className}>
      <h2 className="text-xl font-bold text-zinc-900">{heading}</h2>
      <div className="mt-6 flex flex-col gap-8 sm:flex-row sm:gap-8">
        {figures.map((figure) => (
          <Figure key={figure.label} label={figure.label}>
            {figure.content}
          </Figure>
        ))}
      </div>
    </Card>
  )
}

export default SynthesizedLogic
