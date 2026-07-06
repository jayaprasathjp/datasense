import { useState } from 'react'
import { formatCurrency } from '../../lib/format'

const GRID_STEPS = [0, 0.25, 0.5, 0.75, 1]
const CHART_HEIGHT = 200

function niceMax(value) {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  return Math.ceil(value / magnitude) * magnitude
}

function GroupedBarChart({ data, seriesKeys, colors, valueFormatter = formatCurrency }) {
  const [hover, setHover] = useState(null)
  const max = niceMax(Math.max(...data.flatMap((d) => seriesKeys.map((k) => d[k] ?? 0))))

  return (
    <div className="w-full">
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2">
        {seriesKeys.map((key) => (
          <span key={key} className="inline-flex items-center gap-1.5 font-sans text-xs text-zinc-700">
            <span
              aria-hidden="true"
              className="h-2.5 w-2.5 shrink-0 rounded-[2px]"
              style={{ backgroundColor: colors[key] }}
            />
            {key}
          </span>
        ))}
      </div>

      <div className="flex">
        <div
          className="flex shrink-0 flex-col justify-between pr-3 text-right font-sans text-[11px] tabular-nums text-zinc-500"
          style={{ height: CHART_HEIGHT }}
        >
          {[...GRID_STEPS].reverse().map((step) => (
            <span key={step}>{valueFormatter(max * step)}</span>
          ))}
        </div>

        <div className="relative flex-1">
          <div
            className="absolute inset-0 flex flex-col justify-between"
            aria-hidden="true"
          >
            {GRID_STEPS.map((step) => (
              <div key={step} className="h-px w-full bg-zinc-200" />
            ))}
          </div>

          <div className="relative flex items-end justify-around gap-6" style={{ height: CHART_HEIGHT }}>
            {data.map((group) => (
              <div key={group.region} className="flex h-full flex-1 items-end justify-center gap-[3px]">
                {seriesKeys.map((key) => {
                  const value = group[key] ?? 0
                  const heightPct = (value / max) * 100
                  const cellId = `${group.region}-${key}`
                  return (
                    <div
                      key={key}
                      className="relative flex h-full w-full max-w-[24px] items-end"
                      onMouseEnter={() => setHover(cellId)}
                      onMouseLeave={() => setHover((h) => (h === cellId ? null : h))}
                    >
                      {hover === cellId && (
                        <div className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-xs font-semibold tabular-nums text-zinc-900 shadow-md">
                          {valueFormatter(value)}
                        </div>
                      )}
                      <div
                        className="w-full rounded-t-[4px]"
                        style={{ height: `${heightPct}%`, backgroundColor: colors[key] }}
                      />
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-2 flex items-end justify-around gap-6 pl-[52px]">
        {data.map((group) => (
          <span
            key={group.region}
            className="flex-1 text-center font-sans text-[11px] uppercase tracking-[0.06em] text-zinc-600"
          >
            {group.region}
          </span>
        ))}
      </div>
    </div>
  )
}

export default GroupedBarChart
