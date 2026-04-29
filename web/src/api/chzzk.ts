import { requestJson } from './client'

type RequestOptions = {
  signal?: AbortSignal
}

type ListOptions = RequestOptions & {
  limit?: number
}

export type ChzzkCategoryOverview = {
  chzzk_category_id: string
  category_name: string
  category_type: string
  latest_bucket_time: string
  latest_viewers_observed: number
  observed_bucket_count: number
  bucket_time_min: string
  bucket_time_max: string
  viewer_hours_observed: number
  avg_viewers_observed: number
  peak_viewers_observed: number
  live_count_observed_total: number
  avg_channels_observed: number
  peak_channels_observed: number
  viewer_per_channel_observed: number | null
  unique_channels_observed: number | null
  full_1d_candidate_available: boolean
  full_7d_candidate_available: boolean
  missing_1d_bucket_count: number
  missing_7d_bucket_count: number
  coverage_status: string
  bounded_sample_caveat: string
}

function withQuery(path: string, query: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams()

  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined) {
      params.set(key, String(value))
    }
  })

  const search = params.toString()
  return search.length > 0 ? `${path}?${search}` : path
}

function listCategoryOverview(options: ListOptions = {}): Promise<ChzzkCategoryOverview[]> {
  return requestJson<ChzzkCategoryOverview[]>(
    withQuery('/chzzk/categories/overview', { limit: options.limit ?? 50 }),
    { signal: options.signal },
  )
}

export const chzzkApi = {
  listCategoryOverview,
}
