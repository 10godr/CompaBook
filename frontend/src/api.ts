// Cliente de la API. Mismo origen que la web, así que la cookie de sesión viaja sola.
const BASE = import.meta.env.VITE_API_URL ?? '/api/v1'

export class ApiError extends Error {
  status: number
  code: string
  retryAfter?: number
  reason?: string

  constructor(status: number, code: string, message: string, extra: { retryAfter?: number; reason?: string } = {}) {
    super(message)
    this.status = status
    this.code = code
    this.retryAfter = extra.retryAfter
    this.reason = extra.reason
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; retry_after?: number; reason?: string }
}

interface Options {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
}

export async function api<T = unknown>(path: string, { method = 'GET', body }: Options = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      credentials: 'same-origin',
      // Todo POST exige esta cabecera: un formulario de otro sitio no puede añadirla.
      headers: {
        'X-Requested-With': 'compabook',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'network', 'Sin conexión con el servidor')
  }

  const data: unknown = await response.json().catch(() => undefined)
  if (!response.ok) {
    const error = (data as ErrorBody | undefined)?.error
    throw new ApiError(response.status, error?.code ?? 'unknown', error?.message ?? 'Error inesperado', {
      retryAfter: error?.retry_after,
      reason: error?.reason,
    })
  }
  return data as T
}
