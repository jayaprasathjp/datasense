import Card from '../ui/Card'
import SectionLabel from '../ui/SectionLabel'

function InquirySidebar({ heading = 'Inquiries', items = [], activeIndex = 0, onSelect }) {
  return (
    <Card>
      <SectionLabel className="px-2 pb-3 pt-1">{heading}</SectionLabel>
      <nav>
        <ul className="flex flex-col gap-1">
          {items.map((item, index) => {
            const isActive = index === activeIndex
            return (
              <li key={item}>
                <button
                  type="button"
                  onClick={() => onSelect?.(index)}
                  className={`w-full rounded-lg px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-[#e8edf2] text-[#1e3a5f]'
                      : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900'
                  }`}
                >
                  {item}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>
    </Card>
  )
}

export default InquirySidebar
