import { createContext, useContext } from 'react'

export interface User {
  email: string
  language: 'es' | 'en'
  timezone: string
}

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated'

export interface AuthState {
  status: AuthStatus
  user: User | null
  login: (email: string, password: string) => Promise<void>
  setUser: (user: User) => void
  logout: () => Promise<void>
  /** Da la sesión por cerrada en este dispositivo, sin llamar a la API (p. ej. tras eliminar la cuenta). */
  clearSession: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return context
}
