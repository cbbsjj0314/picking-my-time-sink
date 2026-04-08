import { useEffect, useState } from 'react'
import logoLockup from '../assets/ui/brand/header-symbol.png'
import headerWordmark from '../assets/ui/brand/header-wordmark.png'

interface StickyShellProps {
  searchApplied: boolean
  searchDirty: boolean
  searchValue: string
  searchPending: boolean
  onReset: () => void
  onSearchChange: (value: string) => void
  onSearchSubmit: () => void
}

function SearchIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-5 w-5"
      fill="none"
      viewBox="0 0 20 20"
    >
      <circle cx="8.25" cy="8.25" r="4.75" stroke="currentColor" strokeWidth="2" />
      <path d="M11.8 11.8L16 16" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  )
}

export function StickyShell({
  searchApplied,
  searchDirty,
  searchValue,
  searchPending,
  onReset,
  onSearchChange,
  onSearchSubmit,
}: StickyShellProps) {
  const [searchOpen, setSearchOpen] = useState(false)
  const hasSearchValue = searchValue.length > 0

  const handleReset = () => {
    setSearchOpen(false)
    onReset()
  }

  useEffect(() => {
    if (!searchOpen) {
      return
    }

    const handlePointerDown = (event: Event) => {
      const target = event.target

      if (!(target instanceof Element)) {
        return
      }

      if (!target.closest('[data-search-shell="true"]')) {
        setSearchOpen(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [searchOpen])

  return (
    <div className="sticky top-0 z-40 border-b border-transparent">
      <div className="shell-panel glass-blur">
        <div className="mx-auto flex max-w-[1520px] items-center justify-between gap-3 px-4 py-2 sm:gap-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4 lg:gap-5">
            <button
              aria-label="Return to default dashboard view"
              className="shrink-0 outline-none transition-opacity hover:opacity-85 focus-visible:opacity-85"
              onClick={handleReset}
              type="button"
            >
              <img
                alt="Picking My Time Sink logo"
                className="h-14 w-auto object-contain sm:h-[4.25rem] lg:h-[4.5rem]"
                src={logoLockup}
              />
            </button>
            <button
              aria-label="Return to default dashboard view"
              className="flex h-10 min-w-0 max-w-[180px] flex-1 items-center overflow-hidden outline-none transition-opacity hover:opacity-85 focus-visible:opacity-85 sm:h-12 sm:max-w-[230px] md:h-14 md:max-w-[280px] lg:h-16 lg:max-w-[360px] xl:h-[4.5rem] xl:max-w-[410px]"
              onClick={handleReset}
              type="button"
            >
              <img
                alt="Picking My Time Sink wordmark"
                className="w-full max-w-none shrink-0"
                src={headerWordmark}
              />
            </button>
          </div>

          <div className="flex shrink-0 items-center justify-end gap-3 lg:gap-4">
            <div
              className={`flex h-12 shrink-0 overflow-hidden rounded-2xl transition-[width,box-shadow,background-color,outline-color] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
                searchOpen
                  ? 'surface-etched panel-worn ghost-outline w-[180px] shadow-[0_14px_30px_rgba(0,0,0,0.12)] sm:w-[220px] md:w-[280px] lg:w-[340px] xl:w-[420px]'
                  : 'w-12 bg-transparent shadow-none outline-transparent'
              }`}
              data-search-shell="true"
            >
              <button
                aria-expanded={searchOpen}
                aria-label={searchOpen ? 'Search open' : 'Open search'}
                className={`relative flex h-full shrink-0 items-center justify-center text-[var(--text-secondary)] transition ${
                  searchOpen
                    ? 'w-12 text-[var(--text-muted)]'
                    : 'w-full rounded-2xl hover:bg-[rgba(118,108,95,0.14)] hover:text-[var(--text-primary)]'
                }`}
                onClick={() => {
                  if (!searchOpen) {
                    setSearchOpen(true)
                  }
                }}
                type="button"
              >
                <SearchIcon />
                {(searchPending || hasSearchValue || searchApplied || searchDirty) && (
                  <span
                    className={`absolute right-2 top-2 h-2 w-2 rounded-full ${
                      searchPending
                        ? 'bg-[var(--wine)] shadow-[0_0_10px_rgba(109,79,75,0.32)]'
                        : searchDirty
                          ? 'bg-[var(--amber)] shadow-[0_0_10px_rgba(184,121,41,0.22)]'
                          : 'bg-[rgba(96,74,55,0.28)]'
                    }`}
                  />
                )}
              </button>

              <input
                autoFocus={searchOpen}
                className={`h-full min-w-0 bg-transparent text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] transition-[width,opacity,padding] duration-200 ${
                  searchOpen ? 'w-full pr-3 pl-1 opacity-100' : 'w-0 px-0 opacity-0'
                }`}
                onChange={(event: { target: HTMLInputElement }) => onSearchChange(event.target.value)}
                onKeyDown={(event: { key: string }) => {
                  if (event.key === 'Enter') {
                    onSearchSubmit()
                  }

                  if (event.key === 'Escape') {
                    setSearchOpen(false)
                  }
                }}
                placeholder="Search"
                tabIndex={searchOpen ? 0 : -1}
                value={searchValue}
              />
            </div>

            <div className="surface-etched panel-worn ghost-outline hidden h-12 flex-1 items-center justify-center rounded-2xl px-4 text-sm text-[var(--text-muted)] lg:flex lg:min-w-[132px]">
              Profile
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
