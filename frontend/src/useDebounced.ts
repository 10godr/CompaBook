import { useEffect, useState } from 'react'

// El valor, pero solo cuando deja de cambiar durante `delay` ms (para no buscar en cada tecla).
export function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
