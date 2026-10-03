import { requestJson } from './client'

export type CombinedGameActivity = {
  canonical_game_id: number
  canonical_name: string
  steam_appid: number | null
  ccu_period_anchor_date: string | null
  period_avg_ccu_7d: number | null
  period_peak_ccu_7d: number | null
  chzzk_mapped_category_count: number
  chzzk_viewer_hours_observed_7d: number | null
  chzzk_peak_viewers_observed_7d: number | null
  chzzk_observed_bucket_count_7d: number | null
  chzzk_collection_bucket_count_7d: number | null
  chzzk_observation_ratio_7d: number | null
  chzzk_latest_observed_bucket_7d: string | null
  bounded_sample_caveat: 'bounded_sample'
}

export const COMBINED_ACTIVITY_LIMIT = 200

export function listGameActivity(signal?: AbortSignal): Promise<CombinedGameActivity[]> {
  return requestJson<CombinedGameActivity[]>(
    `/combined/games/activity?limit=${COMBINED_ACTIVITY_LIMIT}`,
    { signal },
  )
}
