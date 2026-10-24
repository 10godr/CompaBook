import { describe, expect, it } from 'vitest'

import { api, ApiError } from './api'
import { apiError, mockApi } from './test/mockApi'

describe('api', () => {
  it('manda la cabecera anti-CSRF y usa la cookie del mismo origen', async () => {
    const calls = mockApi({ 'GET /me': { body: { ok: true } } })
    await api('/me')
    expect(calls[0].headers['X-Requested-With']).toBe('compabook')
  })

  it('envía el cuerpo como JSON en un POST', async () => {
    const calls = mockApi({ 'POST /auth/login': { body: {} } })
    await api('/auth/login', { method: 'POST', body: { email: 'a@b.c' } })
    expect(calls[0].body).toEqual({ email: 'a@b.c' })
    expect(calls[0].headers['Content-Type']).toBe('application/json')
  })

  it('no manda Content-Type si no hay cuerpo', async () => {
    const calls = mockApi({ 'GET /me': { body: {} } })
    await api('/me')
    expect(calls[0].headers['Content-Type']).toBeUndefined()
  })

  it('convierte un error de la API en ApiError con su código, espera y motivo', async () => {
    mockApi({ 'POST /auth/login': apiError(429, 'rate_limited', { retry_after: 900 }) })
    await expect(api('/auth/login', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 429,
      code: 'rate_limited',
      retryAfter: 900,
    })
  })

  it('conserva el motivo de una contraseña débil', async () => {
    mockApi({ 'POST /auth/register': apiError(422, 'weak_password', { reason: 'too_common' }) })
    await expect(api('/auth/register', { method: 'POST', body: {} })).rejects.toMatchObject({
      code: 'weak_password',
      reason: 'too_common',
    })
  })

  it('un error sin cuerpo JSON es unknown', async () => {
    mockApi({ 'GET /me': { status: 502, body: undefined } })
    const error = await api('/me').catch((failure: unknown) => failure)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('unknown')
  })

  it('una red caída es un ApiError network', async () => {
    mockApi({})
    await expect(api('/me')).rejects.toMatchObject({ status: 0, code: 'network' })
  })
})
