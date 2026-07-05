function SectionLabel({ children, className = '' }) {
  return (
    <p
      className={`text-xs font-semibold uppercase tracking-wider text-zinc-500 ${className}`}
    >
      {children}
    </p>
  )
}

export default SectionLabel
