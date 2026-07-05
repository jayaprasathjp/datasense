const TONE_STYLES = {
  good: { color: '#15803d', bg: '#dcfce7' },
  warning: { color: '#b45309', bg: '#fef3c7' },
  critical: { color: '#b91c1c', bg: '#fee2e2' },
  neutral: { color: '#3f3f46', bg: '#f4f4f5' },
}

function Badge({ tone = 'neutral', children }) {
  const { color, bg } = TONE_STYLES[tone]
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{ color, backgroundColor: bg }}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      {children}
    </span>
  )
}

export default Badge
