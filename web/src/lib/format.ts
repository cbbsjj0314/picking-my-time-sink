export const formatWon = (value: number) =>
  new Intl.NumberFormat('ko-KR', {
    style: 'currency',
    currency: 'KRW',
    maximumFractionDigits: 0,
  }).format(value)

export const formatCompact = (value: number) =>
  new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: value >= 1000 ? 1 : 0,
  }).format(value)

export const formatSignedPercent = (value: number, digits = 1) => {
  const sign = value > 0 ? '▲' : value < 0 ? '▼' : '•'
  return `${sign} ${Math.abs(value).toFixed(digits)}%`
}

export const formatSignedPoints = (value: number, digits = 1) => {
  const sign = value > 0 ? '▲' : value < 0 ? '▼' : '•'
  return `${sign} ${Math.abs(value).toFixed(digits)}%p`
}

export const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

export const hashString = (value: string) =>
  value.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)
