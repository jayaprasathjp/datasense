function Metric({ label, run }) {
  if (!run || run.status === 'pending') {
    return (
      <span>
        {label}: <span className="text-zinc-400">queued</span>
      </span>
    )
  }
  if (run.status === 'active') {
    return (
      <span>
        {label}: <span className="text-[#1e3a5f]">running…</span>
      </span>
    )
  }
  if (run.status === 'error') {
    return (
      <span>
        {label}: <span className="font-semibold text-red-700">failed</span>
      </span>
    )
  }
  return (
    <span>
      {label}:{' '}
      <span className="font-semibold tabular-nums text-zinc-900">{run.seconds.toFixed(2)}s</span>
    </span>
  )
}

function BenchmarkStrip({ cpu, gpu }) {
  const bothDone = cpu?.status === 'done' && gpu?.status === 'done'
  const gpuFaster = bothDone && gpu.seconds < cpu.seconds
  const multiplier = bothDone
    ? gpuFaster
      ? cpu.seconds / gpu.seconds
      : gpu.seconds / cpu.seconds
    : null

  const anyError = cpu?.status === 'error' || gpu?.status === 'error'
  const borderColor = bothDone ? (gpuFaster ? '#15803d' : '#b45309') : anyError ? '#dc2626' : '#a1a1aa'

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-zinc-200 bg-white px-5 py-3.5 text-sm"
      style={{ borderLeft: `3px solid ${borderColor}` }}
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-zinc-500">
        <Metric label="CPU baseline" run={cpu} />
        <Metric label="GPU accelerated" run={gpu} />
        {cpu?.status === 'error' && <span className="text-xs text-red-600">CPU: {cpu.error}</span>}
        {gpu?.status === 'error' && <span className="text-xs text-red-600">GPU: {gpu.error}</span>}
      </div>
      {bothDone && (
        <span
          className="text-sm font-semibold"
          style={{ color: borderColor }}
        >
          {gpuFaster
            ? `${multiplier.toFixed(1)}x faster on GPU`
            : `${multiplier.toFixed(1)}x — GPU overhead at this row count`}
        </span>
      )}
    </div>
  )
}

export default BenchmarkStrip
