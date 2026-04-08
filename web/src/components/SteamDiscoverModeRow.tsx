import type { SteamDiscoverMode } from '../types'
import { ModeShellRow } from './ModeShellRow'

interface SteamDiscoverModeRowProps {
  mode: SteamDiscoverMode
  onChange: (mode: SteamDiscoverMode) => void
}

const items = [
  {
    value: 'Top Selling',
    label: 'Top Selling',
    description: 'Steam에서 상점 매출이 높은 게임 보기',
  },
  {
    value: 'Most Played',
    label: 'Most Played',
    description: 'Steam에서 많이 플레이되고 있는 게임 보기',
  },
] as const satisfies ReadonlyArray<{ value: SteamDiscoverMode; label: string; description: string }>

export function SteamDiscoverModeRow({ mode, onChange }: SteamDiscoverModeRowProps) {
  return <ModeShellRow items={items} onChange={onChange} selected={mode} />
}
