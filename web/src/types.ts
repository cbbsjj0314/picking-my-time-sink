export const sourceTabs = ['Combined', 'Steam', 'Chzzk'] as const
export const discoverModes = ['Trending', 'Co-Moving'] as const
export const steamDiscoverModes = ['Explore', 'Top Selling'] as const
export const rangeOptions = ['1D', 'Last 7 Days', 'Last 30 Days', 'Last 3 Months'] as const
export const timelineRanges = ['1D', '7D', '30D', '90D'] as const
export const steamChartRanges = ['7D', '30D', '90D'] as const
export const steamDataStateKinds = ['Pending', 'Partial', 'Stale'] as const
export const steamDataStateTargets = ['CCU', 'Reviews', 'Price'] as const

export type SourceTab = (typeof sourceTabs)[number]
export type DiscoverMode = (typeof discoverModes)[number]
export type SteamDiscoverMode = (typeof steamDiscoverModes)[number]
export type RangeOption = (typeof rangeOptions)[number]
export type TimelineRange = (typeof timelineRanges)[number]
export type SteamChartRange = (typeof steamChartRanges)[number]
export type SteamDataStateKind = (typeof steamDataStateKinds)[number]
export type SteamDataStateTarget = (typeof steamDataStateTargets)[number]

export const steamDiscoverModeDisplayLabels: Record<SteamDiscoverMode, string> = {
  Explore: 'Explore',
  'Top Selling': 'Top Selling',
}

export function getSteamDiscoverModeDisplayLabel(mode: SteamDiscoverMode): string {
  return steamDiscoverModeDisplayLabels[mode]
}

export interface TimelinePoint {
  label: string
  ccu: number
  viewers: number
}

export interface SignalCardData {
  label: string
  accent: 'streaming' | 'positive' | 'warning' | 'neutral'
  rows: Array<{ label: string; value: string }>
}

export interface SentimentPanel {
  keywords: string[]
  likes: string[]
  dislikes: string[]
}

export interface CombinedWhySurfacedNowPanel {
  summary: string
  streamingNow: string
  steamNow: string
}

export interface ContextGame {
  id: string
  title: string
  rank: number
  reviewsDelta: string
  price: string
  ccuDelta: string
  viewerDelta: string
  signalBadge: string
  verdicts: string[]
  signalCards: SignalCardData[]
  sentiment: SentimentPanel
  whySurfacedNow: CombinedWhySurfacedNowPanel
  timeline: Record<TimelineRange, TimelinePoint[]>
}

export interface SteamCcuPoint {
  label: string
  ccu: number
}

export interface SteamDataState {
  kind: SteamDataStateKind
  target: SteamDataStateTarget
  tooltip: string
}

export interface SteamChartState {
  kind: 'loading' | 'empty' | 'error'
  message: string
}

export interface SteamDetailCard {
  label: string
  subtitle?: string
  rows: Array<{ label: string; value: string }>
}

export interface SteamReferenceGame {
  id: string
  canonicalGameId: number | null
  title: string
  rank: number
  liveCcu: string
  priceLine: string
  reviewSummary: string
  statusBadge: SteamDataStateKind | null
  verdictChips: string[]
  surfaceContext: string
  detailCards: SteamDetailCard[]
  timeline: Record<SteamChartRange, SteamCcuPoint[]>
  cardStates?: Partial<Record<SteamDataStateTarget, SteamDataState>>
  chartState?: SteamChartState
}
