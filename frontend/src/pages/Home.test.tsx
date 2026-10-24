import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ANA, apiError, mockApi } from '../test/mockApi'
import { detail, me, page, summary } from '../test/concepts'
import { renderApp } from '../test/render'

const pathname = () => window.location.pathname
const nobody = page([])

// Guardia de la prueba H de la cookie (docs/pruebas-riesgo.md): con la sesión abierta, la app
// instalada abre en Inicio y no tiene barra de direcciones, así que el enlace tiene que estar.
describe('Inicio (temporal, Fase 4)', () => {
  it('con sesión, enlaza a las pruebas de cookie y de push', async () => {
    mockApi({ 'GET /me': { body: { user: ANA } } })
    renderApp('/')
    expect(await screen.findByRole('link', { name: 'Prueba de cookie' })).toHaveAttribute('href', '/prueba-cookie')
    expect(screen.getByRole('link', { name: 'Prueba de push' })).toHaveAttribute('href', '/prueba-push')
  })
})

describe('Inicio: añadir un concepto', () => {
  it('muestra el campo, el uso del día y los últimos conceptos', async () => {
    mockApi({
      'GET /me': me(3, 30),
      'GET /concepts?limit=5': page([summary({ id: 'a', title: 'Docker' }), summary({ id: 'b', title: 'Redis' })]),
    })
    renderApp('/')
    expect(await screen.findByLabelText('¿Qué concepto quieres entender?')).toBeInTheDocument()
    expect(await screen.findByText('3 de 30 conceptos hoy')).toBeInTheDocument()
    const links = await screen.findAllByRole('link', { name: /Docker|Redis/ })
    expect(links.map((link) => link.getAttribute('href'))).toEqual(['/cuaderno/a', '/cuaderno/b'])
    expect(screen.getByRole('link', { name: 'Ver todo el Cuaderno' })).toHaveAttribute('href', '/cuaderno')
  })

  it('añade el concepto y abre su ficha, que pone en marcha la generación', async () => {
    let generated = false
    const calls = mockApi({
      'GET /me': me(),
      'GET /concepts?limit=5': nobody,
      'POST /concepts': { status: 201, body: { id: 'nuevo', status: 'pending' } },
      'GET /concepts/nuevo': () => ({ body: generated ? detail({ id: 'nuevo' }) : detail({ id: 'nuevo', status: 'pending', stage: 'queued', card: null }) }),
      'POST /concepts/nuevo/process': () => {
        generated = true
        return { body: { status: 'completed', stage: 'done', attempts: 0 } }
      },
    })
    const { user } = renderApp('/')
    await user.type(await screen.findByLabelText('¿Qué concepto quieres entender?'), '  CI/CD ')
    await user.click(screen.getByRole('button', { name: 'Añadir' }))

    expect(await screen.findByRole('heading', { name: 'CI/CD' })).toBeInTheDocument()
    expect(pathname()).toBe('/cuaderno/nuevo')
    expect(calls.find((call) => call.path === '/concepts' && call.method === 'POST')?.body).toEqual({ title: 'CI/CD' })
    expect(calls.filter((call) => call.path === '/concepts/nuevo/process')).toHaveLength(1)
  })

  it('el botón está apagado sin texto o con solo espacios', async () => {
    mockApi({ 'GET /me': me(), 'GET /concepts?limit=5': nobody })
    const { user } = renderApp('/')
    const add = await screen.findByRole('button', { name: 'Añadir' })
    expect(add).toBeDisabled()
    await user.type(screen.getByLabelText('¿Qué concepto quieres entender?'), '   ')
    expect(add).toBeDisabled()
    await user.type(screen.getByLabelText('¿Qué concepto quieres entender?'), 'a')
    expect(add).toBeEnabled()
  })

  it('con el límite del día alcanzado no deja añadir y lo explica', async () => {
    mockApi({ 'GET /me': me(30, 30), 'GET /concepts?limit=5': nobody })
    const { user } = renderApp('/')
    await user.type(await screen.findByLabelText('¿Qué concepto quieres entender?'), 'Algo')
    expect(await screen.findByText('Llegaste al límite de hoy. Mañana podrás añadir más.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Añadir' })).toBeDisabled()
  })

  it('si la API dice que se llegó al límite, lo muestra y vuelve a leer el uso', async () => {
    const calls = mockApi({
      'GET /me': me(29, 30),
      'GET /concepts?limit=5': nobody,
      'POST /concepts': apiError(429, 'daily_limit_reached', { limit: 30, retry_after: 3600 }),
    })
    const { user } = renderApp('/')
    await user.type(await screen.findByLabelText('¿Qué concepto quieres entender?'), 'Algo')
    await user.click(screen.getByRole('button', { name: 'Añadir' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Llegaste al límite de conceptos de hoy')
    expect(pathname()).toBe('/')
    await waitFor(() => expect(calls.filter((call) => call.path === '/me')).toHaveLength(3)) // sesión, uso y uso de nuevo
  })

  it('el contador n/200 solo aparece cuando se acerca al tope', async () => {
    mockApi({ 'GET /me': me(), 'GET /concepts?limit=5': nobody })
    const { user } = renderApp('/')
    const field = await screen.findByLabelText('¿Qué concepto quieres entender?')
    expect(field).toHaveAttribute('maxlength', '200')
    await user.type(field, 'a'.repeat(100))
    expect(screen.queryByText('100/200')).not.toBeInTheDocument()
    await user.type(field, 'a'.repeat(70))
    expect(screen.getByText('170/200')).toBeInTheDocument()
  })

  it('sin conceptos lo dice', async () => {
    mockApi({ 'GET /me': me(), 'GET /concepts?limit=5': nobody })
    renderApp('/')
    expect(await screen.findByText('Todavía no has añadido ninguno.')).toBeInTheDocument()
  })

  it('un título con etiquetas HTML se pinta literal', async () => {
    mockApi({
      'GET /me': me(),
      'GET /concepts?limit=5': page([summary({ title: '<b>negrita</b> & <img src=x>' })]),
    })
    const { container } = renderApp('/')
    const link = await screen.findByRole('link', { name: /negrita/ })
    expect(within(link).getByText('<b>negrita</b> & <img src=x>')).toBeInTheDocument()
    expect(container.querySelector('b, img')).toBeNull()
  })
})
