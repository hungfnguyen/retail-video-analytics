type TabItem<T extends string> = {
  id: T
  label: string
  badge?: string | number
}

type TabsProps<T extends string> = {
  value: T
  onChange: (v: T) => void
  items: Array<TabItem<T>>
}

export function Tabs<T extends string>({ value, onChange, items }: TabsProps<T>) {
  return (
    <div className="flex border-b border-slate-200">
      {items.map((item) => {
        const isActive = item.id === value
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onChange(item.id)}
            className={
              isActive
                ? 'relative -mb-px flex items-center gap-1.5 border-b-2 border-blue-600 px-4 py-2.5 text-sm font-semibold text-blue-600'
                : 'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium text-slate-500 hover:text-slate-800 transition-colors'
            }
          >
            {item.label}
            {item.badge !== undefined && (
              <span className={`rounded-full px-1.5 py-0.5 text-[11px] font-semibold ${isActive ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-500'}`}>
                {item.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
