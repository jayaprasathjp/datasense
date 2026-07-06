function Masthead({
  kicker = 'Data Intelligence Platform',
  title = 'FleetPulse / GPU',
  tagline = 'GPU-accelerated order intelligence — pricing risk, demand spikes, and fulfillment triage, computed live against real e-commerce order data.',
}) {
  const slashIndex = title.indexOf('/')
  const prefix = slashIndex === -1 ? title : title.slice(0, slashIndex)
  const suffix = slashIndex === -1 ? '' : title.slice(slashIndex)

  return (
    <header className="w-full py-10">
      {kicker && (
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-[#1e3a5f]">
          {kicker}
        </p>
      )}
      <h1 className="font-serif text-4xl font-semibold tracking-tight text-zinc-900 sm:text-5xl">
        {prefix}
        {suffix && <span className="text-[#1e3a5f]">{suffix}</span>}
      </h1>
      <p className="mt-3 max-w-2xl text-sm text-zinc-500">{tagline}</p>
      <div className="mt-6 h-px w-full max-w-2xl bg-zinc-300" />
    </header>
  )
}

export default Masthead
