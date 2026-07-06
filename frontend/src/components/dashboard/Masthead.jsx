function Masthead({
  title = 'FleetPulse / GPU',
  tagline = 'GPU-accelerated bottleneck detection for global delivery networks — weather, volume spikes, and vehicle breakdowns, caught before they cascade.',
}) {
  return (
    <header className="w-full py-10">
      <h1 className="text-3xl font-extrabold tracking-tight text-zinc-900 sm:text-4xl">
        {title}
      </h1>
      <p className="mt-2 max-w-2xl text-sm text-zinc-500">{tagline}</p>
    </header>
  )
}

export default Masthead
