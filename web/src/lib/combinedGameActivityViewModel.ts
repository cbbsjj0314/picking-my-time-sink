import type { CombinedGameActivity } from '../api/combinedActivity'

export function buildCombinedActivityPoints(rows: CombinedGameActivity[], searchQuery: string) {
  const query = searchQuery.trim().toLowerCase()
  return rows.flatMap((row) => {
    const x = row.period_avg_ccu_7d
    const y = row.chzzk_viewer_hours_observed_7d
    if (x === null || y === null) return []
    if (query && ![row.canonical_name, String(row.canonical_game_id), String(row.steam_appid ?? '')]
      .some((value) => value.toLowerCase().includes(query))) return []

    return [{
      id: row.canonical_game_id,
      name: row.canonical_name,
      anchorDate: row.ccu_period_anchor_date,
      x,
      y,
      label: `${row.canonical_name} (ID ${row.canonical_game_id}): Steam average CCU ${x}; Chzzk observed viewer-hours ${y}; 7 KST dates ending ${row.ccu_period_anchor_date}; bounded_sample`,
    }]
  })
}
