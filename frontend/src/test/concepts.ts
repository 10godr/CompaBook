import type { CardContent, ConceptDetail, ConceptSummary, Video } from '../concepts/types'
import { ANA } from './mockApi'

export const CARD: CardContent = {
  canonical_title: 'CI/CD',
  what_is: 'Qué es.',
  what_for: 'Para qué sirve.',
  example: 'Un ejemplo.',
  example_code: null,
  example_code_language: null,
}

export const VIDEOS: Video[] = [
  {
    youtube_id: 'abcdefghij1',
    title: 'CI/CD en 10 minutos',
    channel: 'Canal Uno',
    thumbnail_url: 'https://i.ytimg.com/vi/abcdefghij1/hqdefault.jpg',
  },
  {
    youtube_id: 'abcdefghij2',
    title: 'Qué es CI/CD',
    channel: null,
    thumbnail_url: 'https://i.ytimg.com/vi/abcdefghij2/hqdefault.jpg',
  },
]

export function summary(override: Partial<ConceptSummary> = {}): ConceptSummary {
  return {
    id: 'c1',
    title: 'CI/CD',
    language: 'es',
    created_at: '2026-10-24T12:00:00Z',
    card_title: null,
    status: 'completed',
    stage: 'done',
    attempts: 0,
    ...override,
  }
}

export function detail(override: Partial<ConceptDetail> = {}): ConceptDetail {
  return { ...summary(), source: 'app', card: CARD, videos: [], ...override }
}

// GET /me con el uso del día.
export function me(used = 3, limit = 30) {
  return { body: { user: ANA, usage: { concepts_today: used, daily_limit: limit } } }
}

export function page(items: ConceptSummary[], next: string | null = null) {
  return { body: { items, next_cursor: next } }
}
