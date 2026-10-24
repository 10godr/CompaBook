import { describe, expect, it } from 'vitest'

import { ApiError } from './api'
import { errorMessage, isEmail } from './errors'
import i18n, { setLanguage } from './i18n'

const t = i18n.t.bind(i18n)

describe('errorMessage', () => {
  it('traduce los códigos conocidos', () => {
    expect(errorMessage(t, new ApiError(401, 'invalid_credentials', ''))).toBe(
      'El correo o la contraseña no son correctos.',
    )
    expect(errorMessage(t, new ApiError(403, 'registration_not_allowed', ''))).toBe(
      'El registro es solo por invitación.',
    )
    expect(errorMessage(t, new ApiError(400, 'invalid_code', ''))).toContain('código no es correcto')
  })

  it('cambia con el idioma', () => {
    setLanguage('en')
    expect(errorMessage(t, new ApiError(401, 'invalid_credentials', ''))).toBe(
      'The email or password is incorrect.',
    )
  })

  it('redondea la espera hacia arriba, en minutos', () => {
    expect(errorMessage(t, new ApiError(429, 'rate_limited', '', { retryAfter: 900 }))).toContain('15 min')
    expect(errorMessage(t, new ApiError(429, 'rate_limited', '', { retryAfter: 61 }))).toContain('2 min')
    expect(errorMessage(t, new ApiError(429, 'rate_limited', '', { retryAfter: 5 }))).toContain('1 min')
  })

  it('sin espera conocida usa un mensaje genérico', () => {
    expect(errorMessage(t, new ApiError(429, 'rate_limited', ''))).toContain('en un momento')
  })

  it('explica por qué una contraseña es débil', () => {
    expect(errorMessage(t, new ApiError(422, 'weak_password', '', { reason: 'too_short' }))).toContain('8 caracteres')
    expect(errorMessage(t, new ApiError(422, 'weak_password', '', { reason: 'too_common' }))).toContain('común')
  })

  it('un motivo desconocido cae en un mensaje de validación', () => {
    expect(errorMessage(t, new ApiError(422, 'weak_password', '', { reason: 'raro' }))).toContain('Revisa los datos')
  })

  it('un código desconocido o un error que no es de la API da el mensaje genérico', () => {
    expect(errorMessage(t, new ApiError(500, 'algo_nuevo', ''))).toContain('Algo salió mal')
    expect(errorMessage(t, new Error('x'))).toContain('Algo salió mal')
  })

  it('la red caída tiene su propio mensaje', () => {
    expect(errorMessage(t, new ApiError(0, 'network', ''))).toContain('conexión')
  })
})

describe('isEmail', () => {
  it.each(['ana@example.com', ' ana@example.com ', 'a.b+c@sub.dominio.org'])('acepta %s', (value) => {
    expect(isEmail(value)).toBe(true)
  })

  it.each(['', 'ana', 'ana@', '@example.com', 'ana@example', 'a na@example.com'])('rechaza "%s"', (value) => {
    expect(isEmail(value)).toBe(false)
  })
})
