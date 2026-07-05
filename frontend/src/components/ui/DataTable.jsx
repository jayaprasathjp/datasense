function DataTable({ columns, rows, keyField = 'rank' }) {
  return (
    <div className="w-full overflow-x-auto rounded-xl border border-zinc-200">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="bg-zinc-50">
            {columns.map((col) => (
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
          {rows.map((row) => (
            <tr key={row[keyField]} className="border-b border-zinc-100 last:border-b-0 hover:bg-zinc-50/70">
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-4 py-3 tabular-nums text-zinc-800 ${
                    col.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                >
                  {col.render ? col.render(row) : row[col.key]}
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
