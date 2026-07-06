import DataTable from '../ui/DataTable'
import BenchmarkStrip from './BenchmarkStrip'

function noRowsMessage(cpu, gpu) {
  const cpuErrored = cpu?.status === 'error'
  const gpuErrored = gpu?.status === 'error'
  const cpuEmpty = cpu?.status === 'done' && !(cpu.results?.length > 0)
  const gpuEmpty = gpu?.status === 'done' && !(gpu.results?.length > 0)

  if (cpuErrored && gpuErrored) {
    return 'Both the CPU and GPU runs failed. See the errors above.'
  }
  if (cpuErrored && gpuEmpty) {
    return 'The CPU run failed, and the GPU run completed but returned no rows — check the GPU logs for the underlying execution error.'
  }
  if (gpuErrored && cpuEmpty) {
    return 'The GPU run failed, and the CPU run completed but returned no rows.'
  }
  if (cpuEmpty && gpuEmpty) {
    return 'Both runs completed but returned no rows.'
  }
  return null
}

function InquiryOutput({ cpu, gpu, synthesisError }) {
  const idle = (!cpu || cpu.status === 'pending') && (!gpu || gpu.status === 'pending')

  if (synthesisError) {
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700">
        Code synthesis failed: {synthesisError}
      </p>
    )
  }

  if (idle) {
    return (
      <p className="rounded-xl border border-dashed border-zinc-300 px-4 py-8 text-center text-sm text-zinc-500">
        Click Execute to run this query against the live dataset.
      </p>
    )
  }

  const gpuHasRows = gpu?.status === 'done' && gpu.results?.length > 0
  const cpuHasRows = cpu?.status === 'done' && cpu.results?.length > 0
  const rows = gpuHasRows ? gpu.results : cpuHasRows ? cpu.results : null
  const source = gpuHasRows ? 'GPU' : cpuHasRows ? 'CPU' : null

  const settled = (s) => s?.status === 'done' || s?.status === 'error'
  const bothSettled = settled(cpu) && settled(gpu)
  const emptyMessage = bothSettled ? noRowsMessage(cpu, gpu) : null
  const emptyIsError = cpu?.status === 'error' || gpu?.status === 'error'

  return (
    <div className="flex flex-col gap-6">
      <BenchmarkStrip cpu={cpu} gpu={gpu} />

      {rows ? (
        <div className="flex flex-col gap-2">
          {source && (
            <p className="text-xs text-zinc-500">
              Showing results from the {source} run{source === 'CPU' ? ' (GPU run failed or returned no rows)' : ''}.
            </p>
          )}
          <DataTable rows={rows} />
        </div>
      ) : (
        emptyMessage && (
          <p
            className={`rounded-xl border px-4 py-4 text-sm ${
              emptyIsError
                ? 'border-red-200 bg-red-50 text-red-700'
                : 'border-zinc-200 bg-zinc-50 text-zinc-600'
            }`}
          >
            {emptyMessage}
          </p>
        )
      )}
    </div>
  )
}

export default InquiryOutput
