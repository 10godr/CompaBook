import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ANA, apiError, mockApi } from '../test/mockApi'
import { renderApp } from '../test/render'

const session = { 'GET /me': { body: { user: ANA } } }
const pathname = () => window.location.pathname
const posts = (calls: ReturnType<typeof mockApi>) => calls.filter((call) => call.method !== 'GET')

describe('idioma de la cuenta', () => {
  it('al cambiar el idioma se guarda en la cuenta y cambia la web', async () => {
    const calls = mockApi({
      ...session,
      'PATCH /me': { body: { user: { ...ANA, language: 'en' } } },
    })
    const { user } = renderApp('/ajustes')
    await user.selectOptions(await screen.findByLabelText('Idioma'), 'English')
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    const patch = calls.find((call) => call.method === 'PATCH')
    expect(patch?.path).toBe('/me')
    expect(patch?.body).toEqual({ language: 'en' })
  })

  it('si la API falla, el idioma cambia igualmente en el dispositivo', async () => {
    mockApi(session) // el PATCH no está simulado: falla como una red caída
    const { user } = renderApp('/ajustes')
    await user.selectOptions(await screen.findByLabelText('Idioma'), 'English')
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })
})

describe('cambiar la contraseña', () => {
  async function fill(user: ReturnType<typeof renderApp>['user'], current: string, next: string) {
    const card = (await screen.findByRole('heading', { name: 'Cambiar contraseña' })).closest('form') as HTMLElement
    if (current) await user.type(within(card).getByLabelText('Contraseña actual'), current)
    if (next) await user.type(within(card).getByLabelText('Contraseña nueva'), next)
    await user.click(within(card).getByRole('button', { name: 'Cambiar contraseña' }))
    return card
  }

  it('cambia la contraseña, avisa y vacía los campos', async () => {
    const calls = mockApi({ ...session, 'POST /me/change-password': { body: { ok: true } } })
    const { user } = renderApp('/ajustes')
    const card = await fill(user, 'caballo-grapa-azul', 'nueva-clave-segura-9')
    expect(await screen.findByRole('status')).toHaveTextContent('Contraseña cambiada')
    expect(within(card).getByLabelText('Contraseña actual')).toHaveValue('')
    expect(calls.find((call) => call.path === '/me/change-password')?.body).toEqual({
      current_password: 'caballo-grapa-azul',
      new_password: 'nueva-clave-segura-9',
    })
  })

  it('contraseña actual incorrecta', async () => {
    mockApi({ ...session, 'POST /me/change-password': apiError(400, 'wrong_password') })
    const { user } = renderApp('/ajustes')
    await fill(user, 'incorrecta-123', 'nueva-clave-segura-9')
    expect((await screen.findByRole('alert')).textContent).toBe('La contraseña actual no es correcta.')
  })

  it('contraseña nueva débil explica el motivo', async () => {
    mockApi({
      ...session,
      'POST /me/change-password': apiError(422, 'weak_password', { reason: 'too_common' }),
    })
    const { user } = renderApp('/ajustes')
    await fill(user, 'caballo-grapa-azul', 'password123')
    expect((await screen.findByRole('alert')).textContent).toContain('demasiado común')
  })

  it('con demasiados intentos dice cuánto esperar', async () => {
    mockApi({
      ...session,
      'POST /me/change-password': apiError(429, 'rate_limited', { retry_after: 600 }),
    })
    const { user } = renderApp('/ajustes')
    await fill(user, 'caballo-grapa-azul', 'nueva-clave-segura-9')
    expect((await screen.findByRole('alert')).textContent).toContain('10 min')
  })

  it('no llama a la API si faltan datos', async () => {
    const calls = mockApi(session)
    const { user } = renderApp('/ajustes')
    await fill(user, '', 'corta')
    expect(await screen.findByText('Escribe tu contraseña.')).toBeInTheDocument()
    expect(screen.getByText('La contraseña debe tener al menos 8 caracteres.')).toBeInTheDocument()
    expect(posts(calls)).toHaveLength(0)
  })
})

describe('eliminar la cuenta', () => {
  async function openDialog(user: ReturnType<typeof renderApp>['user']) {
    await user.click(await screen.findByRole('button', { name: 'Eliminar mi cuenta' }))
    return screen.findByRole('dialog', { name: '¿Eliminar tu cuenta?' })
  }

  it('pide confirmación y no borra nada hasta confirmar', async () => {
    const calls = mockApi(session)
    const { user } = renderApp('/ajustes')
    const dialog = await openDialog(user)
    expect(dialog).toHaveTextContent('de forma definitiva')
    expect(posts(calls)).toHaveLength(0)
  })

  it('cancelar cierra el diálogo y no llama a la API', async () => {
    const calls = mockApi(session)
    const { user } = renderApp('/ajustes')
    const dialog = await openDialog(user)
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(posts(calls)).toHaveLength(0)
  })

  it('Escape también cierra el diálogo', async () => {
    mockApi(session)
    const { user } = renderApp('/ajustes')
    await openDialog(user)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('con la contraseña, borra la cuenta y lleva a la bienvenida', async () => {
    const calls = mockApi({ ...session, 'DELETE /me': { body: { ok: true } } })
    const { user } = renderApp('/ajustes')
    const dialog = await openDialog(user)
    await user.type(within(dialog).getByLabelText('Contraseña'), 'caballo-grapa-azul')
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar cuenta' }))
    await waitFor(() => expect(pathname()).toBe('/bienvenida'))
    expect(calls.find((call) => call.method === 'DELETE')?.body).toEqual({ password: 'caballo-grapa-azul' })
    // La cuenta ya no existe: no se intenta cerrar sesión en la API.
    expect(calls.some((call) => call.path === '/auth/logout')).toBe(false)
  })

  it('con la contraseña incorrecta muestra el error y sigue en Ajustes', async () => {
    mockApi({ ...session, 'DELETE /me': apiError(400, 'wrong_password') })
    const { user } = renderApp('/ajustes')
    const dialog = await openDialog(user)
    await user.type(within(dialog).getByLabelText('Contraseña'), 'incorrecta-123')
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar cuenta' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('La contraseña actual no es correcta.')
    expect(pathname()).toBe('/ajustes')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('sin escribir la contraseña no llama a la API', async () => {
    const calls = mockApi(session)
    const { user } = renderApp('/ajustes')
    const dialog = await openDialog(user)
    await user.click(within(dialog).getByRole('button', { name: 'Eliminar cuenta' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Escribe tu contraseña.')
    expect(posts(calls)).toHaveLength(0)
  })

  it('el diálogo se puede volver a abrir limpio tras cancelar', async () => {
    mockApi(session)
    const { user } = renderApp('/ajustes')
    let dialog = await openDialog(user)
    await user.type(within(dialog).getByLabelText('Contraseña'), 'algo')
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
    dialog = await openDialog(user)
    expect(within(dialog).getByLabelText('Contraseña')).toHaveValue('')
  })
})
