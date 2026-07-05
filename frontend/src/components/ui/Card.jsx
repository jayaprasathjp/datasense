function Card({ children, className = '' }) {
  return (
    <div
      className={`rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm sm:p-8 ${className}`}
    >
      {children}
    </div>
  )
}

export default Card
