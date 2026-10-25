// Formas de las respuestas de /concepts (diseno-tecnico.md §7).
export type JobStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type JobStage = 'queued' | 'writing' | 'finding_videos' | 'done'

export interface JobState {
  status: JobStatus
  stage: JobStage
  attempts: number
}

export interface ConceptSummary extends JobState {
  id: string
  title: string
  language: 'es' | 'en'
  created_at: string
  card_title: string | null
}

export interface CardContent {
  canonical_title: string
  what_is: string
  what_for: string
  example: string
  example_code: string | null
  example_code_language: string | null
}

export interface Video {
  youtube_id: string
  title: string
  channel: string | null
  thumbnail_url: string
}

export interface ConceptDetail extends ConceptSummary {
  source: string
  card: CardContent | null
  videos: Video[]
}

export interface ConceptPage {
  items: ConceptSummary[]
  next_cursor: string | null
}

export interface Usage {
  concepts_today: number
  daily_limit: number
}

// El trabajo sigue en marcha: hay que seguir preguntando por su estado.
export function isActive(status: JobStatus): boolean {
  return status === 'pending' || status === 'processing'
}

export const POLL_MS = 2000
// Pasado este tiempo se deja de preguntar y se avisa de que tarda más de lo normal.
export const GIVE_UP_MS = 3 * 60 * 1000
