import { useCallback, useEffect, useState } from 'react'

import { api } from '../api'
import type { Usage } from './types'

// Cuántos conceptos lleva hoy el usuario y cuál es su tope (GET /me → usage).
export function useUsage() {
  const [usage, setUsage] = useState<Usage | null>(null)

  // Sin el contador la pantalla funciona igual: la API es quien aplica el límite.
  const read = useCallback(() => api<{ usage?: Usage }>('/me').then((data) => data.usage ?? null), [])

  useEffect(() => {
    let cancelled = false
    read()
      .then((value) => {
        if (!cancelled) setUsage(value)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [read])

  const refresh = useCallback(() => {
    read()
      .then(setUsage)
      .catch(() => undefined)
  }, [read])

  return { usage, refresh }
}
