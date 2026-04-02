import type { ReactNode } from "react";

type SectionFrameProps = {
  id?: string;
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
  delayMs?: number;
  children: ReactNode;
};

export function SectionFrame({
  id,
  eyebrow,
  title,
  description,
  action,
  delayMs = 0,
  children,
}: SectionFrameProps) {
  return (
    <section
      id={id}
      className="animate-section-enter border-b border-white/10 pb-10 last:border-b-0 last:pb-0"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-3">
          <p className="text-[0.68rem] uppercase tracking-[0.34em] text-cyan-300/80">
            {eyebrow}
          </p>
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight text-white md:text-3xl">
              {title}
            </h2>
            <p className="max-w-3xl text-sm leading-7 text-slate-400">{description}</p>
          </div>
        </div>
        {action ? <div>{action}</div> : null}
      </div>
      {children}
    </section>
  );
}
