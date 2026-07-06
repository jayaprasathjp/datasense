function Pill({ children, onClick, type = 'button', disabled = false, className = '' }) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center rounded-lg bg-[#1e3a5f] px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#16293f] active:bg-[#0f1f33] disabled:cursor-not-allowed disabled:bg-zinc-300 ${className}`}
    >
      {children}
    </button>
  )
}

export default Pill
