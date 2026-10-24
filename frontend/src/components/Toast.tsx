import { useEffect } from 'react'

// Confirmación breve encima de la barra de navegación; se cierra sola a los 4 s.
export default function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 4000)
    return () => clearTimeout(timer)
  }, [message, onClose])

  return (
    <div className="toast" role="status">
      {message}
    </div>
  )
}
