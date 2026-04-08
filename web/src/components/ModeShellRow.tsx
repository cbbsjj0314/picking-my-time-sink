interface ModeShellItem<T extends string> {
  value: T
  label: string
  description: string
}

interface ModeShellRowProps<T extends string> {
  items: readonly ModeShellItem<T>[]
  selected: T
  onChange: (value: T) => void
}

export function ModeShellRow<T extends string>({ items, selected, onChange }: ModeShellRowProps<T>) {
  return (
    <section className="mx-auto mt-4 max-w-[1520px] px-4 sm:mt-5 sm:px-6 lg:mt-6 lg:px-8">
      <div className="surface-low panel-worn ghost-outline flex flex-col gap-2 rounded-[24px] p-1.5 shadow-[0_8px_24px_rgba(0,0,0,0.14)] md:flex-row md:items-stretch">
        {items.map((item) => {
          const isSelected = item.value === selected

          return (
            <button
              key={item.value}
              className={`flex-1 rounded-[20px] px-5 py-3.5 text-left transition sm:px-6 sm:py-4 ${
                isSelected
                  ? 'bg-[#E8639B] shadow-[inset_0_0_0_1px_rgba(255,224,237,0.28),inset_0_0_0_5px_rgba(22,12,18,0.7),0_10px_24px_rgba(125,43,79,0.12)]'
                  : 'hover:bg-[rgba(96,74,55,0.04)]'
              }`}
              onClick={() => onChange(item.value)}
              type="button"
            >
              <div className="flex items-center justify-between">
                <span className={`type-display text-[1.05rem] font-bold sm:text-[1.18rem] ${isSelected ? 'text-[#2d1820]' : 'text-[var(--text-primary)]'}`}>
                  {item.label}
                </span>
                <span
                  className={`h-2 w-2 rounded-full ${
                    isSelected ? 'bg-[rgba(22,12,18,0.82)] shadow-[0_0_12px_rgba(22,12,18,0.14)]' : 'bg-[rgba(96,74,55,0.16)]'
                  }`}
                />
              </div>
              <p className={`mt-1.5 max-w-none text-[0.95rem] leading-7 md:max-w-[300px] lg:max-w-[380px] ${isSelected ? 'text-[rgba(45,24,32,0.78)]' : 'text-[var(--text-secondary)]'}`}>
                {item.description}
              </p>
            </button>
          )
        })}
      </div>
    </section>
  )
}
