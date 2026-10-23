// Página temporal de la Fase 4 (prueba de la cookie en Safari y en la PWA). Se elimina al cerrar la fase.
import { useState } from 'react'

const API = '/api/v1/poc/cookie'
const MARK_KEY = 'cb_poc_mark'

function isStandalone(): boolean {
  const iosStandalone = (navigator as Navigator & { standalone?: boolean }).standalone
  return window.matchMedia('(display-mode: standalone)').matches || iosStandalone === true
}

export default function PruebaCookie() {
  const [lines, setLines] = useState<string[]>([])

  function log(message: string) {
    setLines((current) => [`${new Date().toLocaleTimeString()} ${message}`, ...current])
  }

  async function call(method: 'POST' | 'GET' | 'DELETE') {
    try {
      const response = await fetch(API, {
        method,
        headers: method === 'GET' ? {} : { 'X-Requested-With': 'compabook' },
      })
      log(`${method} → ${response.status} ${await response.text()}`)
    } catch {
      log(`${method} → error de red`)
    }
  }

  function saveMark() {
    localStorage.setItem(MARK_KEY, new Date().toISOString())
    log('localStorage: marca guardada')
  }

  function readMark() {
    log(`localStorage: ${localStorage.getItem(MARK_KEY) ?? 'sin marca'}`)
  }

  return (
    <>
      <h1>Prueba de cookie</h1>
      <div className="card">
        <p>Modo PWA instalada: {isStandalone() ? 'sí' : 'no (navegador)'}</p>
        <button onClick={() => call('POST')}>Crear cookie</button>
        <button onClick={() => call('GET')}>Ver estado</button>
        <button onClick={() => call('DELETE')}>Borrar cookie</button>
        <button onClick={saveMark}>Guardar marca en localStorage</button>
        <button onClick={readMark}>Leer marca de localStorage</button>
      </div>
      <div className="card">
        {lines.length === 0 ? <p>Sin resultados todavía.</p> : null}
        {lines.map((line) => (
          <code key={line}>{line}</code>
        ))}
      </div>
    </>
  )
}
