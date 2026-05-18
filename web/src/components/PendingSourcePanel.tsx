import type { SourceTab } from '../types'

interface PendingSourcePanelProps {
  sourceTab: Extract<SourceTab, 'Combined'>
}

const copyBySource: Record<Extract<SourceTab, 'Combined'>, { title: string; body: string; note: string }> = {
  Combined: {
    title: 'Combined 소스는 아직 준비 중',
    body: 'Steam과 Chzzk 관측 데이터를 하나의 판단 화면으로 합치는 기능은 아직 준비 중이다.',
    note: '현재는 Steam source view와 Chzzk observed source view를 각각 분리해서 제공한다.',
  },
}

export function PendingSourcePanel({ sourceTab }: PendingSourcePanelProps) {
  const copy = copyBySource[sourceTab]

  return (
    <section className="lg:col-span-2">
      <div className="surface-low panel-worn ghost-outline rounded-[28px] p-6 sm:p-8">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">{sourceTab}</p>
          <h2 className="type-display paper-ink mt-3 text-[2rem] font-bold leading-none sm:text-[2.3rem] xl:text-[2.5rem]">
            {copy.title}
          </h2>
          <p className="mt-5 text-sm leading-7 text-[var(--text-secondary)]">{copy.body}</p>
          <div className="surface-high panel-worn mt-6 rounded-[24px] p-5">
            <p className="type-display text-[1rem] font-bold text-[var(--paper)]">현재 상태</p>
            <p className="mt-3 text-sm leading-7 text-[rgba(244,232,214,0.72)]">{copy.note}</p>
          </div>
        </div>
      </div>
    </section>
  )
}
