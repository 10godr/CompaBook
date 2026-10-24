// Página temporal de la Fase 4 (prueba de push en iPhone). Se elimina al cerrar la fase.
import { useState } from 'react'

const API = '/api/v1/poc/push'

function isStandalone(): boolean {
  const iosStandalone = (navigator as Navigator & { standalone?: boolean }).standalone
  return window.matchMedia('(display-mode: standalone)').matches || iosStandalone === true
}

function supported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

function keyToBytes(base64Url: string): Uint8Array<ArrayBuffer> {
  const padded = base64Url.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(base64Url.length / 4) * 4, '=')
  const raw = atob(padded)
  const bytes = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
  return bytes
}

export default function PruebaPush() {
  const [lines, setLines] = useState<string[]>([])

  function log(message: string) {
    setLines((current) => [`${new Date().toLocaleTimeString()} ${message}`, ...current])
  }

  async function currentSubscription(): Promise<PushSubscription | null> {
    const registration = await navigator.serviceWorker.getRegistration('/')
    return registration ? registration.pushManager.getSubscription() : null
  }

  async function status() {
    log(`PWA instalada: ${isStandalone() ? 'sí' : 'no'}`)
    log(`Soporte de push: ${supported() ? 'sí' : 'no'}`)
    if (!supported()) return
    log(`Permiso: ${Notification.permission}`)
    const subscription = await currentSubscription()
    log(`Suscripción: ${subscription ? new URL(subscription.endpoint).hostname : 'ninguna'}`)
  }

  async function activate() {
    if (!supported()) return log('Este navegador no admite push')
    try {
      // El permiso se pide dentro del gesto del usuario, antes de cualquier otra espera.
      const permission = await Notification.requestPermission()
      log(`Permiso: ${permission}`)
      if (permission !== 'granted') return

      await navigator.serviceWorker.register('/sw.js')
      const registration = await navigator.serviceWorker.ready

      const response = await fetch(`${API}/key`)
      if (!response.ok) return log(`Clave pública: error ${response.status}`)
      const { publicKey } = (await response.json()) as { publicKey: string }

      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyToBytes(publicKey),
      })
      log(`Suscrito en ${new URL(subscription.endpoint).hostname}`)
    } catch (error) {
      log(`Error al activar: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  async function send(delay: number) {
    const subscription = await currentSubscription()
    if (!subscription) return log('Primero activa las notificaciones')
    log(delay > 0 ? `Enviando en ${delay} s: cierra la app ya` : 'Enviando ahora')
    try {
      const response = await fetch(`${API}/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'compabook' },
        body: JSON.stringify({ subscription: subscription.toJSON(), delay }),
      })
      log(`Envío → ${response.status} ${await response.text()}`)
    } catch {
      log('Envío → error de red')
    }
  }

  return (
    <div className="poc">
      <h1>Prueba de push</h1>
      <div className="card">
        <button onClick={status}>Ver estado</button>
        <button onClick={activate}>Activar notificaciones</button>
        <button onClick={() => send(0)}>Enviar ahora</button>
        <button onClick={() => send(8)}>Enviar en 8 s (cierra la app)</button>
      </div>
      <div className="card">
        {lines.length === 0 ? <p>Sin resultados todavía.</p> : null}
        {lines.map((line, index) => (
          <code key={`${index}-${line}`}>{line}</code>
        ))}
      </div>
    </div>
  )
}
