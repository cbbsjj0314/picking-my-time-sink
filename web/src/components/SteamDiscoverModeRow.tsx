import type { SteamDiscoverMode } from '../types'
import { ModeShellRow } from './ModeShellRow'

interface SteamDiscoverModeRowProps {
  mode: SteamDiscoverMode
  onChange: (mode: SteamDiscoverMode) => void
}

const items = [
  {
    value: 'Explore',
    label: 'Explore',
    description: 'active tracked Steam universe를 7D 플레이, 리뷰, KR 가격 근거 테이블로 보기',
  },
  {
    value: 'Top Selling',
    label: 'Top Selling',
    description: 'Steam weekly top sellers snapshot 기준으로 Top Selling 게임 보기',
  },
] as const satisfies ReadonlyArray<{ value: SteamDiscoverMode; label: string; description: string }>

export function SteamDiscoverModeRow({ mode, onChange }: SteamDiscoverModeRowProps) {
  return <ModeShellRow items={items} onChange={onChange} selected={mode} />
}
