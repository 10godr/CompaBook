import { act, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { apiError, mockApi } from '../test/mockApi'
import { detail, me, page, summary } from '../test/concepts'
import { renderApp } from '../test/render'

const LIST = '/concepts?limit=20'
const session = { 'GET /me': me() }

describe('Cuaderno: lista', () => {
  it('muestra los conceptos con su fecha y la píldora de estado de los que no terminaron', async () => {
    mockApi({
      ...session,
      [`GET ${LIST}`]: page([
        summary({ id: 'a', title: 'Docker' }),
        summary({ id: 'b', title: 'Redis', status: 'processing', stage: 'writing' }),
        summary({ id: 'c', title: 'Kafka', status: 'failed' }),
        summary({ id: 'd', title: 'Git', status: 'pending', stage: 'queued' }),
      ]),
    })
    renderApp('/cuaderno')
    const docker = await screen.findByRole('link', { name: /Docker/ })
    expect(docker).toHaveAttribute('href', '/cuaderno/a')
    expect(docker).toHaveTextContent('24 oct 2026')
    expect(within(docker).queryByText(/Generando|Error|En cola/)).toBeNull()
    expect(within(screen.getByRole('link', { name: /Redis/ })).getByText('Generando…')).toBeInTheDocument()
    expect(within(screen.getByRole('link', { name: /Kafka/ })).getByText('Error')).toBeInTheDocument()
    expect(within(screen.getByRole('link', { name: /Git/ })).getByText('En cola')).toBeInTheDocument()
  })

  it('Cuaderno vacío: titular a dos tonos y botón hacia Inicio', async () => {
    mockApi({ ...session, [`GET ${LIST}`]: page([]) })
    renderApp('/cuaderno')
    expect(await screen.findByRole('heading', { name: /Tu Cuaderno está vacío/ })).toHaveTextContent('Añade tu primer concepto.')
    expect(screen.getByRole('link', { name: 'Ir a Inicio' })).toHaveAttribute('href', '/')
  })

  it('un título con etiquetas HTML se pinta literal', async () => {
    mockApi({ ...session, [`GET ${LIST}`]: page([summary({ title: '<b>x</b>' })]) })
    const { container } = renderApp('/cuaderno')
    expect(await screen.findByText('<b>x</b>')).toBeInTheDocument()
    expect(container.querySelector('b')).toBeNull()
  })

  it('si no carga, avisa y deja reintentar', async () => {
    let fail = true
    mockApi({
      ...session,
      [`GET ${LIST}`]: () => (fail ? apiError(500, 'unknown') : page([summary({ title: 'Docker' })])),
    })
    const { user } = renderApp('/cuaderno')
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cargar tus conceptos.')
    fail = false
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('link', { name: /Docker/ })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('«Cargar más» pide la página siguiente con el cursor y no repite conceptos', async () => {
    const calls = mockApi({
      ...session,
      [`GET ${LIST}`]: page([summary({ id: 'a', title: 'Uno' }), summary({ id: 'b', title: 'Dos' })], 'CURSOR1'),
      [`GET ${LIST}&cursor=CURSOR1`]: page([summary({ id: 'b', title: 'Dos' }), summary({ id: 'c', title: 'Tres' })]),
    })
    const { user } = renderApp('/cuaderno')
    await screen.findByRole('link', { name: /Uno/ })
    await user.click(screen.getByRole('button', { name: 'Cargar más' }))
    expect(await screen.findByRole('link', { name: /Tres/ })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /Dos/ })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Cargar más' })).toBeNull() // era la última página
    expect(calls.some((call) => call.path === `${LIST}&cursor=CURSOR1`)).toBe(true)
  })

  it('si falla «Cargar más», avisa y conserva lo que ya se veía', async () => {
    mockApi({ ...session, [`GET ${LIST}`]: page([summary({ title: 'Uno' })], 'C') })
    const { user } = renderApp('/cuaderno')
    await screen.findByRole('link', { name: /Uno/ })
    await user.click(screen.getByRole('button', { name: 'Cargar más' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Uno/ })).toBeInTheDocument()
  })
})

describe('Cuaderno: búsqueda', () => {
  it('busca al dejar de escribir y trata el texto como texto', async () => {
    const calls = mockApi({
      ...session,
      [`GET ${LIST}`]: page([summary({ id: 'a', title: 'Docker' }), summary({ id: 'b', title: 'CI/CD' })]),
      [`GET ${LIST}&q=ci`]: page([summary({ id: 'b', title: 'CI/CD' })]),
    })
    const { user } = renderApp('/cuaderno')
    await screen.findByRole('link', { name: /Docker/ })
    await user.type(screen.getByLabelText('Buscar en tu Cuaderno'), 'ci')
    await waitFor(() => expect(screen.queryByRole('link', { name: /Docker/ })).toBeNull())
    expect(screen.getByRole('link', { name: /CI\/CD/ })).toBeInTheDocument()
    // No se buscó por cada tecla: solo la lista inicial y la búsqueda final.
    expect(calls.filter((call) => call.path.startsWith('/concepts?'))).toHaveLength(2)
  })

  it('al borrar la búsqueda vuelve la lista completa', async () => {
    mockApi({
      ...session,
      [`GET ${LIST}`]: page([summary({ id: 'a', title: 'Docker' }), summary({ id: 'b', title: 'CI/CD' })]),
      [`GET ${LIST}&q=ci`]: page([summary({ id: 'b', title: 'CI/CD' })]),
    })
    const { user } = renderApp('/cuaderno')
    await screen.findByRole('link', { name: /Docker/ })
    const search = screen.getByLabelText('Buscar en tu Cuaderno')
    await user.type(search, 'ci')
    await waitFor(() => expect(screen.queryByRole('link', { name: /Docker/ })).toBeNull())
    await user.clear(search)
    expect(await screen.findByRole('link', { name: /Docker/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /CI\/CD/ })).toBeInTheDocument()
  })

  it('una respuesta lenta de una búsqueda anterior no pisa la de ahora', async () => {
    let releaseSlow: (reply: ReturnType<typeof page>) => void = () => undefined
    const calls = mockApi({
      ...session,
      [`GET ${LIST}`]: page([summary({ title: 'Inicial' })]),
      [`GET ${LIST}&q=a`]: () => new Promise((resolve) => (releaseSlow = resolve)),
      [`GET ${LIST}&q=ab`]: page([summary({ id: 'n', title: 'Nueva' })]),
    })
    const { user } = renderApp('/cuaderno')
    await screen.findByRole('link', { name: /Inicial/ })
    const search = screen.getByLabelText('Buscar en tu Cuaderno')
    await user.type(search, 'a')
    await waitFor(() => expect(calls.some((call) => call.path.endsWith('&q=a'))).toBe(true))
    await user.type(search, 'b')
    expect(await screen.findByRole('link', { name: /Nueva/ })).toBeInTheDocument()
    releaseSlow(page([summary({ id: 'v', title: 'Vieja' })])) // llega tarde, ya con otra búsqueda
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole('link', { name: /Vieja/ })).toBeNull()
    expect(screen.getByRole('link', { name: /Nueva/ })).toBeInTheDocument()
  })

  it('sin coincidencias lo dice con lo que se buscó', async () => {
    mockApi({
      ...session,
      [`GET ${LIST}`]: page([summary({ title: 'Docker' })]),
      [`GET ${LIST}&q=zzz`]: page([]),
    })
    const { user } = renderApp('/cuaderno')
    await screen.findByRole('link', { name: /Docker/ })
    await user.type(screen.getByLabelText('Buscar en tu Cuaderno'), 'zzz')
    expect(await screen.findByText('No hay conceptos que coincidan con «zzz».')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /vacío/ })).toBeNull() // no es el Cuaderno vacío
  })

  it('los caracteres especiales viajan codificados', async () => {
    const calls = mockApi({
      ...session,
      [`GET ${LIST}`]: page([summary({ title: 'x' })]),
      [`GET ${LIST}&q=100%25+%26+a_b`]: page([]),
    })
    const { user } = renderApp('/cuaderno')
    await screen.findByRole('link', { name: /x/ })
    await user.type(screen.getByLabelText('Buscar en tu Cuaderno'), '100% & a_b')
    await waitFor(() => expect(calls.some((call) => call.path.includes('q=100%25'))).toBe(true))
  })
})

describe('Cuaderno: eliminar', () => {
  async function openDelete(user: ReturnType<typeof renderApp>['user'], title: string) {
    await user.click(await screen.findByRole('button', { name: `Opciones de ${title}` }))
    await user.click(screen.getByRole('menuitem', { name: 'Eliminar' }))
    return screen.getByRole('dialog', { name: '¿Eliminar este concepto?' })
  }

  const two = page([summary({ id: 'a', title: 'Docker' }), summary({ id: 'b', title: 'Redis' })])

  it('pide confirmación, elimina, quita la tarjeta y avisa', async () => {
    const calls = mockApi({ ...session, [`GET ${LIST}`]: two, 'DELETE /concepts/a': { body: { ok: true } } })
    const { user } = renderApp('/cuaderno')
    const dialog = await openDelete(user, 'Docker')
    expect(dialog).toHaveTextContent('«Docker»')
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false) // todavía no
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: /Docker/ })).toBeNull())
    expect(screen.getByRole('link', { name: /Redis/ })).toBeInTheDocument()
    expect(screen.getByText('Concepto eliminado')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(calls.find((call) => call.method === 'DELETE')?.headers['X-Requested-With']).toBe('compabook')
  })

  it('cancelar no elimina nada', async () => {
    const calls = mockApi({ ...session, [`GET ${LIST}`]: two })
    const { user } = renderApp('/cuaderno')
    const dialog = await openDelete(user, 'Docker')
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('link', { name: /Docker/ })).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)
  })

  it('Escape cierra el diálogo sin eliminar', async () => {
    const calls = mockApi({ ...session, [`GET ${LIST}`]: two })
    const { user } = renderApp('/cuaderno')
    await openDelete(user, 'Docker')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)
  })

  it('si ya no existía (404) se quita de la lista igualmente', async () => {
    mockApi({ ...session, [`GET ${LIST}`]: two, 'DELETE /concepts/a': apiError(404, 'not_found') })
    const { user } = renderApp('/cuaderno')
    const dialog = await openDelete(user, 'Docker')
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: /Docker/ })).toBeNull())
  })

  it('si falla, lo explica en el diálogo y no quita la tarjeta', async () => {
    mockApi({ ...session, [`GET ${LIST}`]: two, 'DELETE /concepts/a': apiError(500, 'unknown') })
    const { user } = renderApp('/cuaderno')
    const dialog = await openDelete(user, 'Docker')
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar' }))
    expect(await within(dialog).findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Docker/ })).toBeInTheDocument()
  })

  it('el aviso de «Concepto eliminado» se va solo a los 4 segundos', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockApi({ ...session, [`GET ${LIST}`]: two, 'DELETE /concepts/a': { body: { ok: true } } })
    const { user } = renderApp('/cuaderno')
    const dialog = await openDelete(user, 'Docker')
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar' }))
    expect(await screen.findByText('Concepto eliminado')).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(4100))
    expect(screen.queryByText('Concepto eliminado')).toBeNull()
  })
})

describe('Cuaderno: conceptos en marcha', () => {
  it('se actualiza solo cuando el concepto termina', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let done = false
    mockApi({
      ...session,
      [`GET ${LIST}`]: page([summary({ id: 'a', title: 'Docker', status: 'processing', stage: 'writing' })]),
      'GET /concepts/a/status': () => ({
        body: done ? { status: 'completed', stage: 'done', attempts: 0 } : { status: 'processing', stage: 'writing', attempts: 0 },
      }),
      'GET /concepts/a': () => ({ body: detail({ id: 'a', title: 'Docker', card_title: 'Docker (contenedores)' }) }),
    })
    renderApp('/cuaderno')
    expect(await screen.findByText('Generando…')).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(3100))
    expect(screen.getByText('Generando…')).toBeInTheDocument() // sigue en marcha
    done = true
    await act(() => vi.advanceTimersByTimeAsync(3100))
    await waitFor(() => expect(screen.queryByText('Generando…')).toBeNull())
  })
})
