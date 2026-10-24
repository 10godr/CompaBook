import { vi } from 'vitest'

export interface Reply {
  status?: number
  body?: unknown
}

export interface Call {
  method: string
  path: string
  body: unknown
  headers: Record<string, string>
}

// Una ruta puede ser una respuesta fija o una función (también asíncrona, para controlar cuándo llega).
type Route = Reply | ((body: unknown) => Reply | Promise<Reply>)

// Sustituye `fetch` por una API simulada. Las rutas se escriben como "POST /auth/login".
// Una ruta sin simular hace fallar la petición, igual que una red caída.
export function mockApi(routes: Record<string, Route>): Call[] {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).replace('/api/v1', '')
      const method = init?.method ?? 'GET'
      const body = init?.body ? (JSON.parse(String(init.body)) as unknown) : undefined
      calls.push({ method, path, body, headers: (init?.headers ?? {}) as Record<string, string> })

      const route = routes[`${method} ${path}`]
      if (!route) throw new TypeError(`Sin ruta simulada: ${method} ${path}`)
      const reply = typeof route === 'function' ? await route(body) : route
      return new Response(JSON.stringify(reply.body ?? {}), {
        status: reply.status ?? 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
  return calls
}

export const ANA = { email: 'ana@example.com', language: 'es', timezone: 'America/Santo_Domingo' }

export const anonymous: Record<string, Route> = {
  'GET /me': { status: 401, body: { error: { code: 'unauthorized', message: 'No has iniciado sesión' } } },
}

export function apiError(status: number, code: string, extra: Record<string, unknown> = {}): Reply {
  return { status, body: { error: { code, message: code, ...extra } } }
}
