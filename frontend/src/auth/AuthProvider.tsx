import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, ApiError } from '../api'
import { AuthContext, type AuthState, type AuthStatus, type User } from './context'

interface UserResponse {
  user: User
}

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUserState] = useState<User | null>(null)

  const setUser = useCallback((next: User) => {
    setUserState(next)
    setStatus('authenticated')
  }, [])

  // Al abrir la app se pregunta quién es el usuario; sin sesión vigente la API responde 401.
  useEffect(() => {
    let cancelled = false
    api<UserResponse>('/me')
      .then((data) => {
        if (!cancelled) setUser(data.user)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        // Un fallo de red no cierra la sesión: se trata como sin sesión solo para pintar el acceso.
        if (!(error instanceof ApiError)) console.error(error)
        setUserState(null)
        setStatus('anonymous')
      })
    return () => {
      cancelled = true
    }
  }, [setUser])

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await api<UserResponse>('/auth/login', { method: 'POST', body: { email, password } })
      setUser(data.user)
    },
    [setUser],
  )

  const logout = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST' })
    } catch {
      // Sin conexión o con un error del servidor, en este dispositivo la sesión se da por
      // cerrada igualmente; la sesión del servidor caduca sola a los 30 días sin uso.
    }
    setUserState(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo<AuthState>(
    () => ({ status, user, login, setUser, logout }),
    [status, user, login, setUser, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
