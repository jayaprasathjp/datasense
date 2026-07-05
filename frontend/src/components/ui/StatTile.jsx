function StatTile({ label, value, sublabel }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-2 text-3xl font-bold text-zinc-900">{value}</p>
      {sublabel && <p className="mt-1 text-xs text-zinc-500">{sublabel}</p>}
    </div>
  )
}

export default StatTile
