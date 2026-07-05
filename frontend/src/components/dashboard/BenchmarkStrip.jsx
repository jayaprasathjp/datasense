function BenchmarkStrip({ cpuSeconds, gpuSeconds, note }) {
  const gpuFaster = gpuSeconds < cpuSeconds
  const multiplier = gpuFaster ? cpuSeconds / gpuSeconds : gpuSeconds / cpuSeconds
  const stateColor = gpuFaster ? '#15803d' : '#b45309'

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-zinc-200 bg-white px-5 py-3.5 text-sm"
      style={{ borderLeft: `3px solid ${stateColor}` }}
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-zinc-500">
        <span>
          CPU baseline:{' '}
          <span className="font-semibold tabular-nums text-zinc-900">{cpuSeconds.toFixed(2)}s</span>
        </span>
        <span>
          GPU accelerated:{' '}
          <span className="font-semibold tabular-nums text-zinc-900">{gpuSeconds.toFixed(2)}s</span>
        </span>
        {note && <span className="text-xs text-zinc-400">{note}</span>}
      </div>
      <span className="text-sm font-semibold" style={{ color: stateColor }}>
        {gpuFaster
          ? `${multiplier.toFixed(1)}x faster on GPU`
          : `${multiplier.toFixed(1)}x — GPU overhead at this row count`}
      </span>
    </div>
  )
}

export default BenchmarkStrip
