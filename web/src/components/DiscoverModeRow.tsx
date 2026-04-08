import type { DiscoverMode } from '../types'
import { ModeShellRow } from './ModeShellRow'

interface DiscoverModeRowProps {
  mode: DiscoverMode
  onChange: (mode: DiscoverMode) => void
}

const items = [
  {
    value: 'Trending',
    label: 'Trending',
    description: 'Surface the games pulling the strongest short-term attention right now.',
  },
  {
    value: 'Co-Moving',
    label: 'Co-Moving',
    description: 'Surface titles where players and streaming interest are moving together.',
  },
] as const satisfies ReadonlyArray<{ value: DiscoverMode; label: string; description: string }>

export function DiscoverModeRow({ mode, onChange }: DiscoverModeRowProps) {
  return <ModeShellRow items={items} onChange={onChange} selected={mode} />
}
