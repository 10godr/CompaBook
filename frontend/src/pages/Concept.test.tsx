import { act, render, screen, waitFor, within } from '@testing-library/react'
import { StrictMode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { setLanguage } from '../i18n'
import { apiError, mockApi } from '../test/mockApi'
import { CARD, detail, me } from '../test/concepts'
import App from '../App'
import { renderApp } from '../test/render'

const session = { 'GET /me': me() }
const queued = detail({ status: 'pending', stage: 'queued', card: null })
const writing = detail({ status: 'processing', stage: 'writing', card: null })
const failed = detail({ status: 'failed', stage: 'writing', attempts: 1, card: null })
const STATUS_DONE = { body: { status: 'completed', stage: 'done', attempts: 0 } }

describe('Ficha: generación', () => {
  it('un concepto en cola se pone en marcha una sola vez y termina mostrando la ficha', async () => {
    let generated = false
    const calls = mockApi({
      ...session,
      'GET /concepts/c1': () => ({ body: generated ? detail() : queued }),
      'POST /concepts/c1/process': () => {
        generated = true
        return STATUS_DONE
      },
    })
    renderApp('/cuaderno/c1')
    expect(await screen.findByRole('heading', { name: 'CI/CD' })).toBeInTheDocument()
    expect(screen.getByText('Qué es.')).toBeInTheDocument()
    expect(calls.filter((call) => call.method === 'POST' && call.path.endsWith('/process'))).toHaveLength(1)
    expect(calls.find((call) => call.path.endsWith('/process'))?.headers['X-Requested-With']).toBe('compabook')
  })

  it('en desarrollo (StrictMode monta dos veces) no pide la generación por duplicado', async () => {
    let generated = false
    const calls = mockApi({
      ...session,
      'GET /concepts/c1': () => ({ body: generated ? detail() : queued }),
      'POST /concepts/c1/process': () => {
        generated = true
        return STATUS_DONE
      },
    })
    window.history.pushState({}, '', '/cuaderno/c1')
    render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
    expect(await screen.findByRole('heading', { name: 'CI/CD' })).toBeInTheDocument()
    expect(calls.filter((call) => call.path.endsWith('/process'))).toHaveLength(1)
  })

  it('en cola muestra el panel de carga con el paso actual', async () => {
    mockApi({
      ...session,
      'GET /concepts/c1': { body: queued },
      'POST /concepts/c1/process': () => new Promise<never>(() => undefined), // nunca termina
    })
    renderApp('/cuaderno/c1')
    expect(await screen.findByText('En cola, ya casi le toca…')).toBeInTheDocument()
    const steps = within(screen.getByRole('list', { name: 'Progreso' })).getAllByRole('listitem')
    expect(steps.map((step) => step.textContent)).toEqual(['En cola', 'Escribiendo', '¡Listo!'])
    expect(steps[0]).toHaveAttribute('aria-current', 'step')
    expect(screen.queryByRole('heading', { name: 'CI/CD' })).toBeNull()
  })

  it('si otro proceso ya lo está generando, no lo pide otra vez y sigue su estado hasta el final', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let done = false
    const calls = mockApi({
      ...session,
      'GET /concepts/c1': () => ({ body: done ? detail() : writing }),
      'GET /concepts/c1/status': () => (done ? STATUS_DONE : { body: { status: 'processing', stage: 'writing', attempts: 0 } }),
    })
    renderApp('/cuaderno/c1')
    expect(await screen.findByText('Escribiendo la explicación…')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Progreso' })).getByText('Escribiendo').closest('li')).toHaveAttribute(
      'aria-current',
      'step',
    )
    done = true
    await act(() => vi.advanceTimersByTimeAsync(2100))
    expect(await screen.findByRole('heading', { name: 'CI/CD' })).toBeInTheDocument()
    expect(calls.some((call) => call.path.endsWith('/process'))).toBe(false)
  })

  it('pasados 3 minutos sin terminar avisa de que tarda y deja de preguntar', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const calls = mockApi({
      ...session,
      'GET /concepts/c1': { body: writing },
      'GET /concepts/c1/status': { body: { status: 'processing', stage: 'writing', attempts: 0 } },
    })
    renderApp('/cuaderno/c1')
    await screen.findByText('Escribiendo la explicación…')
    expect(screen.queryByText(/tardando más de lo normal/)).toBeNull()
    await act(() => vi.advanceTimersByTimeAsync(182_000))
    expect(await screen.findByText(/tardando más de lo normal/)).toBeInTheDocument()
    const asked = calls.filter((call) => call.path.endsWith('/status')).length
    await act(() => vi.advanceTimersByTimeAsync(10_000))
    expect(calls.filter((call) => call.path.endsWith('/status')).length).toBe(asked)
  })
})

describe('Ficha: fallo y reintento', () => {
  it('muestra el error con Reintentar, que deja en cola y vuelve a generar', async () => {
    let state: 'failed' | 'pending' | 'done' = 'failed'
    const calls = mockApi({
      ...session,
      'GET /concepts/c1': () => ({ body: state === 'failed' ? failed : state === 'pending' ? queued : detail() }),
      'POST /concepts/c1/retry': () => {
        state = 'pending'
        return { status: 202, body: { status: 'pending', stage: 'queued', attempts: 0 } }
      },
      'POST /concepts/c1/process': () => {
        state = 'done'
        return STATUS_DONE
      },
    })
    const { user } = renderApp('/cuaderno/c1')
    expect(await screen.findByRole('heading', { name: 'No se pudo generar' })).toBeInTheDocument()
    expect(screen.getByText('Tu concepto está guardado. Inténtalo de nuevo.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { name: 'CI/CD' })).toBeInTheDocument()
    const posts = calls.filter((call) => call.method === 'POST').map((call) => call.path)
    expect(posts).toEqual(['/concepts/c1/retry', '/concepts/c1/process'])
  })

  it('si el reintento choca con el límite diario lo explica y sigue en error', async () => {
    mockApi({
      ...session,
      'GET /concepts/c1': { body: failed },
      'POST /concepts/c1/retry': apiError(429, 'daily_limit_reached', { limit: 10, retry_after: 100 }),
    })
    const { user } = renderApp('/cuaderno/c1')
    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Llegaste al límite de conceptos de hoy')
    expect(screen.getByRole('heading', { name: 'No se pudo generar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeEnabled()
  })
})

describe('Ficha: contenido', () => {
  it('muestra las tres secciones como texto, nunca como HTML', async () => {
    mockApi({
      ...session,
      'GET /concepts/c1': {
        body: detail({
          card: { ...CARD, what_is: 'Usa <b>negrita</b> y <script>alert(1)</script>.', what_for: 'Uno\n- dos' },
        }),
      },
    })
    const { container } = renderApp('/cuaderno/c1')
    expect(await screen.findByRole('heading', { name: 'Qué es' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Para qué sirve' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ejemplo' })).toBeInTheDocument()
    expect(screen.getByText('Usa <b>negrita</b> y <script>alert(1)</script>.')).toBeInTheDocument()
    expect(container.querySelector('article b, article script')).toBeNull()
    expect(screen.getByText(/Uno\s*- dos/)).toHaveClass('reading') // los saltos de línea los respeta el CSS
  })

  it('el bloque de código se copia con el botón', async () => {
    mockApi({
      ...session,
      'GET /concepts/c1': {
        body: detail({ card: { ...CARD, example_code: 'on: push\njobs: {}', example_code_language: 'yaml' } }),
      },
    })
    const { user } = renderApp('/cuaderno/c1')
    expect(await screen.findByText('yaml')).toBeInTheDocument()
    expect(screen.getByText(/on: push/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Copiar' }))
    expect(await navigator.clipboard.readText()).toBe('on: push\njobs: {}')
    expect(await screen.findByRole('button', { name: 'Copiado' })).toBeInTheDocument()
  })

  it('sin código de ejemplo no hay bloque, y en la 6a no hay sección de videos', async () => {
    mockApi({ ...session, 'GET /concepts/c1': { body: detail() } })
    renderApp('/cuaderno/c1')
    await screen.findByRole('heading', { name: 'CI/CD' })
    expect(screen.queryByRole('button', { name: 'Copiar' })).toBeNull()
    expect(screen.queryByRole('heading', { name: /Videos/i })).toBeNull()
  })

  it('muestra lo que escribió el usuario solo si es distinto del título de la ficha', async () => {
    mockApi({ ...session, 'GET /concepts/c1': { body: detail({ title: 'ci cd' }) } })
    renderApp('/cuaderno/c1')
    expect(await screen.findByText('Escribiste: ci cd')).toBeInTheDocument()
  })

  it('con el mismo título (aunque cambien mayúsculas) no lo repite', async () => {
    mockApi({ ...session, 'GET /concepts/c1': { body: detail({ title: 'ci/cd' }) } })
    renderApp('/cuaderno/c1')
    await screen.findByRole('heading', { name: 'CI/CD' })
    expect(screen.queryByText(/Escribiste/)).toBeNull()
  })

  it('en inglés, la ficha usa los textos de la interfaz en inglés', async () => {
    mockApi({
      'GET /me': { body: { user: { ...me().body.user, language: 'en' }, usage: { concepts_today: 0, daily_limit: 30 } } },
      'GET /concepts/c1': { body: detail() },
    })
    setLanguage('en')
    renderApp('/cuaderno/c1')
    expect(await screen.findByRole('heading', { name: 'What it is' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "What it's for" })).toBeInTheDocument()
  })
})

describe('Ficha: no disponible', () => {
  it('un concepto que no existe (o es de otro usuario) dice que no se encontró', async () => {
    mockApi({ ...session, 'GET /concepts/ajeno': apiError(404, 'not_found') })
    renderApp('/cuaderno/ajeno')
    expect(await screen.findByText('No encontramos este concepto.')).toBeInTheDocument()
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'Cuaderno' })).toHaveAttribute('href', '/cuaderno')
  })

  it('si falla la carga ofrece reintentar, sin decir que no existe', async () => {
    let fail = true
    mockApi({ ...session, 'GET /concepts/c1': () => (fail ? apiError(500, 'unknown') : { body: detail() }) })
    const { user } = renderApp('/cuaderno/c1')
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cargar tus conceptos.')
    expect(screen.queryByText('No encontramos este concepto.')).toBeNull()
    fail = false
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'CI/CD' })).toBeInTheDocument())
  })
})
