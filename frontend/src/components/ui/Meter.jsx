const TONE_COLORS = {
  good: '#16a34a',
  warning: '#d97706',
  critical: '#dc2626',
  accent: '#4f46e5',
}

function Meter({ value, tone = 'accent', label }) {
  const color = TONE_COLORS[tone]
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)

  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-24 shrink-0 overflow-hidden rounded-full" style={{ backgroundColor: `${color}22` }}>
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-medium tabular-nums text-zinc-600">
        {label ?? `${pct}%`}
      </span>
    </div>
  )
}

export default Meter
