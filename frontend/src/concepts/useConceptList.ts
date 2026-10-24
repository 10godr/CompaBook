import { useCallback, useEffect, useState } from 'react'

import { api } from '../api'
import { GIVE_UP_MS, isActive, type ConceptDetail, type ConceptPage, type ConceptSummary, type JobState } from './types'

const LIST_POLL_MS = 3000

export type ListStatus = 'loading' | 'ready' | 'error'

// Lo último que se recibió y a qué petición (búsqueda + intento) corresponde.
interface Loaded {
  key: string
  items: ConceptSummary[]
  cursor: string | null
  failed: boolean
}

// Una página de conceptos con «cargar más», y al día mientras alguno se está generando.
// Cada cambio de búsqueda pide de nuevo la primera página. «Cargando» no se guarda: se deduce de
// que lo recibido no sea de la petición actual, así una respuesta tardía de una búsqueda anterior
// nunca se confunde con la de ahora.
export function useConceptList(query: string, limit: number) {
  const [attempt, setAttempt] = useState(0)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreFailed, setLoadMoreFailed] = useState(false)
  const key = `${query}\u0000${attempt}`

  const pathFor = useCallback(
    (after?: string | null) => {
      const params = new URLSearchParams({ limit: String(limit) })
      if (query) params.set('q', query)
      if (after) params.set('cursor', after)
      return `/concepts?${params.toString()}`
    },
    [query, limit],
  )

  useEffect(() => {
    let cancelled = false
    api<ConceptPage>(pathFor())
      .then((page) => {
        if (!cancelled) setLoaded({ key, items: page.items, cursor: page.next_cursor, failed: false })
      })
      .catch(() => {
        if (!cancelled) setLoaded({ key, items: [], cursor: null, failed: true })
      })
    return () => {
      cancelled = true
    }
  }, [key, pathFor])

  const reload = useCallback(() => setAttempt((current) => current + 1), [])

  const cursor = loaded?.cursor ?? null
  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return
    setLoadingMore(true)
    setLoadMoreFailed(false)
    try {
      const page = await api<ConceptPage>(pathFor(cursor))
      // Si mientras tanto cambió la búsqueda, esta página ya no pertenece a la lista.
      setLoaded((current) => {
        if (!current || current.key !== key) return current
        // Si entre dos páginas se añadió o se borró algo, no se repite ninguno.
        const fresh = page.items.filter((item) => !current.items.some((existing) => existing.id === item.id))
        return { ...current, items: [...current.items, ...fresh], cursor: page.next_cursor }
      })
    } catch {
      setLoadMoreFailed(true)
    } finally {
      setLoadingMore(false)
    }
  }, [cursor, loadingMore, pathFor, key])

  const remove = useCallback((id: string) => {
    setLoaded((current) => current && { ...current, items: current.items.filter((item) => item.id !== id) })
  }, [])

  // Mientras alguno se genera, se le pregunta su estado cada 3 s (hasta 3 minutos).
  const items = loaded?.items ?? []
  const activeIds = items
    .filter((item) => isActive(item.status))
    .map((item) => item.id)
    .join(',')
  useEffect(() => {
    if (!activeIds) return
    const startedAt = Date.now()
    const patch = (id: string, changes: Partial<ConceptSummary>) =>
      setLoaded(
        (current) =>
          current && { ...current, items: current.items.map((item) => (item.id === id ? { ...item, ...changes } : item)) },
      )
    const timer = setInterval(() => {
      if (Date.now() - startedAt > GIVE_UP_MS) return clearInterval(timer)
      for (const id of activeIds.split(',')) {
        api<JobState>(`/concepts/${id}/status`)
          .then((state) => {
            patch(id, state)
            if (state.status === 'completed') {
              return api<ConceptDetail>(`/concepts/${id}`).then((detail) => patch(id, { card_title: detail.card_title }))
            }
          })
          .catch(() => undefined) // se vuelve a intentar en el siguiente turno
      }
    }, LIST_POLL_MS)
    return () => clearInterval(timer)
  }, [activeIds])

  const status: ListStatus = !loaded || loaded.key !== key ? 'loading' : loaded.failed ? 'error' : 'ready'
  return { items, status, hasMore: cursor !== null, loadingMore, loadMoreFailed, loadMore, reload, remove }
}
