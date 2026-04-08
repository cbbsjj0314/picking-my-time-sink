import type { SourceTab } from '../types'

interface SourceTabsRowProps {
  sourceTab: SourceTab
  onChange: (tab: SourceTab) => void
}

export function SourceTabsRow({ sourceTab, onChange }: SourceTabsRowProps) {
  return (
    <section className="mx-auto mt-4 max-w-[1520px] px-4 sm:mt-5 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {(['Combined', 'Steam', 'Chzzk'] as const).map((tab) => {
          const selected = tab === sourceTab

          return (
            <button
              key={tab}
              className={`type-display rounded-full px-4 py-2.5 text-sm font-semibold transition sm:px-5 ${
                selected
                  ? 'bg-[#E8639B] text-[#2d1820] shadow-[inset_0_0_0_1px_rgba(255,224,237,0.28),inset_0_0_0_2.5px_rgba(22,12,18,0.7),0_8px_18px_rgba(125,43,79,0.18)]'
                  : 'text-[var(--text-secondary)] hover:bg-[rgba(96,74,55,0.06)] hover:text-[var(--text-primary)]'
              }`}
              onClick={() => onChange(tab)}
              type="button"
            >
              {tab}
            </button>
          )
        })}
      </div>
    </section>
  )
}
