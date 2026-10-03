import { useEffect, useState } from 'react'
import { listGameActivity, type CombinedGameActivity } from '../api/combinedActivity'

export function useCombinedGameActivity(enabled: boolean) {
  const [rows, setRows] = useState<CombinedGameActivity[]>([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void listGameActivity(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setRows(result)
      })
      .catch((nextError: unknown) => {
        if (controller.signal.aborted) return
        setRows([])
        setError(nextError instanceof Error ? nextError.message : 'Activity could not be loaded.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [enabled])

  return { rows: enabled ? rows : [], loading, error }
}
