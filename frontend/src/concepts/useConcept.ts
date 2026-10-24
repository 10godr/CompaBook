import { useCallback, useEffect, useRef, useState } from 'react'

import { api, ApiError } from '../api'
import { GIVE_UP_MS, isActive, POLL_MS, type ConceptDetail, type JobState } from './types'

export type Phase = 'loading' | 'ready' | 'missing' | 'error'

// Un concepto con su ficha. Si el trabajo está en cola lo pone en marcha (`/process`) y, mientras
// se genera, pregunta su estado cada 2 s; al terminar pide la ficha. Se usa con `key={id}`:
// al cambiar de concepto el componente se monta de nuevo y todo parte de cero.
export function useConcept(id: string) {
  const [concept, setConcept] = useState<ConceptDetail | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [slow, setSlow] = useState(false)
  const started = useRef(false)

  const fetchDetail = useCallback(
    () =>
      api<ConceptDetail>(`/concepts/${id}`).then(
        (detail) => {
          setConcept(detail)
          setPhase('ready')
        },
        (error: unknown) => setPhase(error instanceof ApiError && error.status === 404 ? 'missing' : 'error'),
      ),
    [id],
  )

  const reload = useCallback(() => {
    setPhase('loading')
    void fetchDetail()
  }, [fetchDetail])

  useEffect(() => {
    void fetchDetail()
  }, [fetchDetail])

  // En cola: se pide la generación una sola vez. Si otro proceso ya la hace, la API responde 202
  // y el sondeo de abajo se encarga del resto.
  const status = concept?.status
  useEffect(() => {
    if (status !== 'pending' || started.current) return
    started.current = true
    api(`/concepts/${id}/process`, { method: 'POST' })
      .then(() => fetchDetail())
      .catch(() => undefined) // el estado real lo da el sondeo; abrir de nuevo el concepto reintenta
  }, [status, id, fetchDetail])

  useEffect(() => {
    if (!status || !isActive(status)) return
    const startedAt = Date.now()
    const timer = setInterval(() => {
      if (Date.now() - startedAt > GIVE_UP_MS) {
        clearInterval(timer)
        setSlow(true)
        return
      }
      api<JobState>(`/concepts/${id}/status`)
        .then((state) => {
          if (isActive(state.status)) setConcept((current) => current && { ...current, ...state })
          else return fetchDetail()
        })
        .catch(() => undefined) // sin red un momento: se vuelve a preguntar en 2 s
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [status, id, fetchDetail])

  // Deja el trabajo en cola otra vez; el efecto de arriba lo pone en marcha. Si falla (límite
  // diario, red), el error lo maneja quien llama.
  const retry = useCallback(async () => {
    const state = await api<JobState>(`/concepts/${id}/retry`, { method: 'POST' })
    started.current = false
    setSlow(false)
    setConcept((current) => current && { ...current, ...state })
  }, [id])

  return { concept, phase, slow, retry, reload }
}
