import { requestJson } from './client'

type RequestOptions = {
  signal?: AbortSignal
}

type ListOptions = RequestOptions & {
  limit?: number
}

export type CombinedGameOverview = {
  canonical_game_id: number
  canonical_name: string
  steam_appid: number | null
  steam_source_available: boolean
  chzzk_mapping_available: boolean
  chzzk_category_id: string | null
  category_name: string | null
  category_type: string | null
  latest_bucket_time: string | null
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

function listGameOverview(options: ListOptions = {}): Promise<CombinedGameOverview[]> {
  return requestJson<CombinedGameOverview[]>(
    withQuery('/combined/games/overview', { limit: options.limit ?? 50 }),
    { signal: options.signal },
  )
}

export const combinedApi = {
  listGameOverview,
}
