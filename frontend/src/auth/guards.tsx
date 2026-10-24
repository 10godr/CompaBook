import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from './context'

function Loading() {
  return <div className="loading" role="status" aria-busy="true" />
}

// Las pantallas de la app solo se ven con sesión; sin ella se va a la bienvenida.
export function RequireAuth() {
  const { status } = useAuth()
  if (status === 'loading') return <Loading />
  if (status === 'anonymous') return <Navigate to="/bienvenida" replace />
  return <Outlet />
}

// Las pantallas de acceso solo se ven sin sesión; con ella se va al inicio.
export function PublicOnly() {
  const { status } = useAuth()
  if (status === 'loading') return <Loading />
  if (status === 'authenticated') return <Navigate to="/" replace />
  return <Outlet />
}
