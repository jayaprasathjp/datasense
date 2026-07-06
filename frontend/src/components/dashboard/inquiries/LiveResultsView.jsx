import DataTable from '../../ui/DataTable'
import SectionLabel from '../../ui/SectionLabel'

/**
 * Generic results view for real API data.
 * Renders whatever rows the backend returns, plus execution logs.
 */
function LiveResultsView({ apiResult }) {
  const { gpu, cpu } = apiResult

  // Try to use GPU results first, fallback to CPU results
  const liveRows = (gpu?.results?.length > 0 ? gpu.results : cpu?.results) ?? []
  const gpuLogs = gpu?.logs ?? []
  const cpuLogs = cpu?.logs ?? []

  // Auto-derive columns from the first row keys
  const columns =
    liveRows.length > 0
      ? Object.keys(liveRows[0]).map((key) => ({
          key,
          header: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
          render: (row) => {
            const val = row[key]
            if (typeof val === 'number') {
              return Number.isInteger(val) ? val.toLocaleString() : val.toFixed(4)
            }
            return String(val ?? '—')
          },
        }))
      : []

  return (
    <div className="flex flex-col gap-8">
      {/* Results table */}
      {liveRows.length > 0 ? (
        <div>
          <SectionLabel className="mb-3">
            Results ({liveRows.length} rows • {gpu?.results?.length > 0 ? 'GPU output' : 'CPU output'})
          </SectionLabel>
          <div className="overflow-x-auto">
            <DataTable columns={columns} rows={liveRows} keyField={Object.keys(liveRows[0])[0]} />
          </div>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">
          No tabular results returned — the query may have returned a scalar or the execution failed.
        </p>
      )}

      {/* Execution logs side by side */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <LogPanel title="GPU Sandbox Logs" logs={gpuLogs} accentColor="#d97706" />
        <LogPanel title="CPU Sandbox Logs" logs={cpuLogs} accentColor="#2563eb" />
      </div>
    </div>
  )
}

function LogPanel({ title, logs, accentColor }) {
  return (
    <div>
      <p
        className="mb-2 text-xs font-semibold uppercase tracking-wider"
        style={{ color: accentColor }}
      >
        {title}
      </p>
      <div className="rounded-xl bg-zinc-50 p-4 font-mono text-[12px] leading-relaxed text-zinc-600">
        {logs.length === 0 ? (
          <span className="text-zinc-400">No logs</span>
        ) : (
          logs.map((line, i) => (
            <div key={i} className="border-b border-zinc-100 py-0.5 last:border-0">
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default LiveResultsView
