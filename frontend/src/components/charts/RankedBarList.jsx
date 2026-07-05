function RankedBarList({ data, labelKey, valueKey, colors, valueFormatter }) {
  const max = Math.max(...data.map((d) => d[valueKey]))

  return (
    <div className="flex flex-col gap-3">
      {data.map((d) => {
        const pct = max > 0 ? (d[valueKey] / max) * 100 : 0
        const color = colors ? colors[d[labelKey]] : '#4f46e5'
        return (
          <div key={d[labelKey]} className="grid grid-cols-[120px_1fr_64px] items-center gap-3">
            <span className="text-xs font-medium text-zinc-600">{d[labelKey]}</span>
            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
              <div
                className="h-full rounded-full"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
            <span className="text-right text-xs font-semibold tabular-nums text-zinc-900">
              {valueFormatter ? valueFormatter(d[valueKey]) : d[valueKey]}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default RankedBarList
