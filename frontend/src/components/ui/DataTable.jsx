function humanizeKey(key) {
  return key
    .split('_')
    .map((word) => (word.toLowerCase() === 'id' ? 'ID' : word[0].toUpperCase() + word.slice(1)))
    .join(' ')
}

function formatValue(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2)
  }
  return String(value)
}

function inferColumns(rows) {
  const sample = rows[0] ?? {}
  return Object.keys(sample).map((key) => ({
    key,
    header: humanizeKey(key),
    align: typeof sample[key] === 'number' ? 'right' : 'left',
  }))
}

function DataTable({ columns, rows }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-6 text-center text-sm text-zinc-500">
        No rows returned.
      </div>
    )
  }

  const resolvedColumns = columns ?? inferColumns(rows)

  return (
    <div className="w-full overflow-x-auto rounded-xl border border-zinc-200">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="bg-zinc-50">
            {resolvedColumns.map((col) => (
              <th
                key={col.key}
                className={`border-b border-zinc-200 px-4 py-3 text-xs font-semibold uppercase tracking-wider text-zinc-500 ${
                  col.align === 'right' ? 'text-right' : 'text-left'
                }`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-zinc-100 last:border-b-0 hover:bg-zinc-50/70">
              {resolvedColumns.map((col) => (
                <td
                  key={col.key}
                  className={`px-4 py-3 tabular-nums text-zinc-800 ${
                    col.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                >
                  {col.render ? col.render(row) : formatValue(row[col.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default DataTable
