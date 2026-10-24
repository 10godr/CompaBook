import type { TFunction } from 'i18next'

import { ApiError } from './api'

// Convierte un error de la API en un mensaje para el usuario, en su idioma.
export function errorMessage(t: TFunction, error: unknown): string {
  if (!(error instanceof ApiError)) return t('auth.errors.unknown')

  if (error.code === 'rate_limited') {
    if (!error.retryAfter) return t('auth.errors.rate_limited_short')
    return t('auth.errors.rate_limited', { minutes: Math.max(1, Math.ceil(error.retryAfter / 60)) })
  }
  if (error.code === 'weak_password' && error.reason) {
    return t(`auth.errors.weak_password.${error.reason}`, { defaultValue: t('auth.errors.validation_error') })
  }
  return t(`auth.errors.${error.code}`, { defaultValue: t('auth.errors.unknown') })
}

// Validación mínima en el navegador; la de verdad la hace siempre la API.
export function isEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}
