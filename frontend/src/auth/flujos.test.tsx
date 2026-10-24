import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ANA, anonymous, apiError, mockApi } from '../test/mockApi'
import { renderApp } from '../test/render'

const homeHeading = () => screen.findByRole('heading', { name: /Entiende cualquier concepto/ })
const pathname = () => window.location.pathname
const alertText = async () => (await screen.findByRole('alert')).textContent

describe('guardas de ruta', () => {
  it('sin sesión, la app lleva a la bienvenida', async () => {
    mockApi(anonymous)
    renderApp('/')
    await homeHeading()
    expect(pathname()).toBe('/bienvenida')
  })

  it('sin sesión, una pantalla privada también lleva a la bienvenida', async () => {
    mockApi(anonymous)
    renderApp('/ajustes')
    await homeHeading()
    expect(pathname()).toBe('/bienvenida')
  })

  it('con sesión, las pantallas de acceso llevan al inicio', async () => {
    mockApi({ 'GET /me': { body: { user: ANA } } })
    renderApp('/entrar')
    await homeHeading()
    await waitFor(() => expect(pathname()).toBe('/'))
  })

  it('una ruta que no existe lleva al inicio', async () => {
    mockApi(anonymous)
    renderApp('/no-existe')
    await homeHeading()
    expect(pathname()).toBe('/bienvenida')
  })

  it('las pruebas temporales de la Fase 4 se ven sin sesión', async () => {
    mockApi(anonymous)
    renderApp('/prueba-cookie')
    expect(await screen.findByRole('heading', { name: 'Prueba de cookie' })).toBeInTheDocument()
    expect(pathname()).toBe('/prueba-cookie')
  })
})

describe('bienvenida', () => {
  it('ofrece crear cuenta y entrar', async () => {
    mockApi(anonymous)
    renderApp('/bienvenida')
    expect(await screen.findByRole('link', { name: 'Crear cuenta' })).toHaveAttribute('href', '/registro')
    expect(screen.getByRole('link', { name: 'Entrar' })).toHaveAttribute('href', '/entrar')
  })

  it('el selector de idioma cambia los textos y el atributo lang', async () => {
    mockApi(anonymous)
    const { user } = renderApp('/bienvenida')
    await user.selectOptions(await screen.findByLabelText('Idioma de la web'), 'English')
    expect(await screen.findByRole('link', { name: 'Create account' })).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('en')
  })
})

describe('login', () => {
  async function fill(user: ReturnType<typeof renderApp>['user'], email = 'ana@example.com', password = 'caballo-grapa-azul') {
    await user.type(await screen.findByLabelText('Correo electrónico'), email)
    await user.type(screen.getByLabelText('Contraseña'), password)
    await user.click(screen.getByRole('button', { name: 'Entrar' }))
  }

  it('entra y lleva al inicio', async () => {
    const calls = mockApi({ ...anonymous, 'POST /auth/login': { body: { user: ANA } } })
    const { user } = renderApp('/entrar')
    await fill(user)
    await waitFor(() => expect(pathname()).toBe('/'))
    const login = calls.find((call) => call.path === '/auth/login')
    expect(login?.body).toEqual({ email: 'ana@example.com', password: 'caballo-grapa-azul' })
  })

  it('no manda nada si faltan datos y marca los campos', async () => {
    const calls = mockApi(anonymous)
    const { user } = renderApp('/entrar')
    await user.click(await screen.findByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('Escribe un correo válido.')).toBeInTheDocument()
    expect(screen.getByText('Escribe tu contraseña.')).toBeInTheDocument()
    expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('aria-invalid', 'true')
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
  })

  it('credenciales incorrectas', async () => {
    mockApi({ ...anonymous, 'POST /auth/login': apiError(401, 'invalid_credentials') })
    const { user } = renderApp('/entrar')
    await fill(user)
    expect(await alertText()).toBe('El correo o la contraseña no son correctos.')
    expect(pathname()).toBe('/entrar')
  })

  it('bloqueo por demasiados intentos, con los minutos que faltan', async () => {
    mockApi({ ...anonymous, 'POST /auth/login': apiError(429, 'rate_limited', { retry_after: 900 }) })
    const { user } = renderApp('/entrar')
    await fill(user)
    expect(await alertText()).toBe('Demasiados intentos. Inténtalo de nuevo en 15 min.')
  })

  it('cuenta sin verificar: ofrece ir a verificar', async () => {
    mockApi({ ...anonymous, 'POST /auth/login': apiError(403, 'email_not_verified') })
    const { user } = renderApp('/entrar')
    await fill(user)
    expect(await alertText()).toBe('Falta verificar tu correo.')
    expect(screen.getByRole('link', { name: 'Verificar mi correo' })).toHaveAttribute('href', '/verificar')
  })

  it('sin conexión', async () => {
    mockApi(anonymous) // el login no está simulado: falla como una red caída
    const { user } = renderApp('/entrar')
    await fill(user)
    expect(await alertText()).toContain('No hay conexión')
  })

  it('el botón de mostrar contraseña la descubre', async () => {
    mockApi(anonymous)
    const { user } = renderApp('/entrar')
    const field = await screen.findByLabelText('Contraseña')
    expect(field).toHaveAttribute('type', 'password')
    await user.click(screen.getByRole('button', { name: 'Mostrar contraseña' }))
    expect(field).toHaveAttribute('type', 'text')
    await user.click(screen.getByRole('button', { name: 'Ocultar contraseña' }))
    expect(field).toHaveAttribute('type', 'password')
  })

  it('enlaza a recuperar contraseña y a crear cuenta', async () => {
    mockApi(anonymous)
    renderApp('/entrar')
    expect(await screen.findByRole('link', { name: '¿Olvidaste tu contraseña?' })).toHaveAttribute('href', '/recuperar')
    expect(screen.getByRole('link', { name: 'Crear cuenta' })).toHaveAttribute('href', '/registro')
  })
})

describe('registro y verificación', () => {
  async function fillRegister(
    user: ReturnType<typeof renderApp>['user'],
    { terms = true, password = 'caballo-grapa-azul' } = {},
  ) {
    await user.type(await screen.findByLabelText('Correo electrónico'), 'ana@example.com')
    await user.type(screen.getByLabelText('Contraseña'), password)
    if (terms) await user.click(screen.getByLabelText('Acepto los términos y la política de privacidad'))
    await user.click(screen.getByRole('button', { name: 'Crear cuenta' }))
  }

  it('registra, pide el código, verifica y entra', async () => {
    const calls = mockApi({
      ...anonymous,
      'POST /auth/register': { status: 202, body: { message: 'ok' } },
      'POST /auth/verify-email': { body: { user: ANA } },
    })
    const { user } = renderApp('/registro')
    await fillRegister(user)

    expect(await screen.findByRole('heading', { name: 'Revisa tu correo' })).toBeInTheDocument()
    expect(pathname()).toBe('/verificar')
    expect(screen.getByText(/ana@example\.com/)).toBeInTheDocument()
    const register = calls.find((call) => call.path === '/auth/register')?.body as Record<string, unknown>
    expect(register).toMatchObject({
      email: 'ana@example.com',
      password: 'caballo-grapa-azul',
      language: 'es',
      accept_terms: true,
    })
    expect(typeof register.timezone).toBe('string')

    await user.click(screen.getAllByRole('textbox')[0])
    await user.keyboard('482913')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))
    await waitFor(() => expect(pathname()).toBe('/'))
    expect(calls.find((call) => call.path === '/auth/verify-email')?.body).toEqual({
      email: 'ana@example.com',
      code: '482913',
    })
  })

  it('correo no invitado', async () => {
    mockApi({ ...anonymous, 'POST /auth/register': apiError(403, 'registration_not_allowed') })
    const { user } = renderApp('/registro')
    await fillRegister(user)
    expect(await alertText()).toBe('El registro es solo por invitación.')
    expect(pathname()).toBe('/registro')
  })

  it('contraseña débil explica el motivo', async () => {
    mockApi({
      ...anonymous,
      'POST /auth/register': apiError(422, 'weak_password', { reason: 'too_common' }),
    })
    const { user } = renderApp('/registro')
    await fillRegister(user)
    expect(await alertText()).toBe('Esa contraseña es demasiado común. Elige otra.')
  })

  it('exige aceptar los términos y una contraseña de 8 caracteres antes de llamar a la API', async () => {
    const calls = mockApi(anonymous)
    const { user } = renderApp('/registro')
    await fillRegister(user, { terms: false, password: 'corta' })
    expect(await screen.findByText('Tienes que aceptar los términos para crear la cuenta.')).toBeInTheDocument()
    expect(screen.getByText('La contraseña debe tener al menos 8 caracteres.')).toBeInTheDocument()
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
  })

  it('cambiar el idioma en el registro cambia la web y el idioma de la cuenta', async () => {
    const calls = mockApi({ ...anonymous, 'POST /auth/register': { status: 202, body: {} } })
    const { user } = renderApp('/registro')
    await user.selectOptions(await screen.findByLabelText('Idioma'), 'English')
    expect(await screen.findByRole('heading', { name: 'Create account' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Password'), 'caballo-grapa-azul')
    await user.click(screen.getByLabelText('I accept the terms and the privacy policy'))
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(pathname()).toBe('/verificar'))
    expect(calls.find((call) => call.path === '/auth/register')?.body).toMatchObject({ language: 'en' })
  })

  it('el código incorrecto muestra el error y vacía las casillas', async () => {
    mockApi({ ...anonymous, 'POST /auth/verify-email': apiError(400, 'invalid_code') })
    const { user } = renderApp('/verificar')
    await user.type(await screen.findByLabelText('Correo electrónico'), 'ana@example.com')
    await user.click(screen.getAllByRole('textbox')[1])
    await user.keyboard('111111')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))
    expect(await alertText()).toContain('El código no es correcto o ya caducó')
    expect((screen.getAllByRole('textbox').slice(1) as HTMLInputElement[]).map((box) => box.value).join('')).toBe('')
  })

  it('no manda el código si faltan dígitos', async () => {
    const calls = mockApi(anonymous)
    const { user } = renderApp('/verificar')
    await user.type(await screen.findByLabelText('Correo electrónico'), 'ana@example.com')
    await user.click(screen.getAllByRole('textbox')[1])
    await user.keyboard('123')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))
    expect(await alertText()).toBe('Escribe los 6 dígitos del código.')
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
  })

  it('reenviar el código avisa y deja el botón en espera', async () => {
    const calls = mockApi({ ...anonymous, 'POST /auth/resend-code': { status: 202, body: {} } })
    const { user } = renderApp('/verificar')
    await user.type(await screen.findByLabelText('Correo electrónico'), 'ana@example.com')
    await user.click(screen.getByRole('button', { name: 'Reenviar código' }))
    expect(await screen.findByRole('status')).toHaveTextContent('te enviamos un código nuevo')
    expect(screen.getByRole('button', { name: /Reenviar en \d+ s/ })).toBeDisabled()
    expect(calls.find((call) => call.path === '/auth/resend-code')?.body).toEqual({
      email: 'ana@example.com',
      purpose: 'verify_email',
      language: 'es',
    })
  })

  it('recuerda mirar el spam', async () => {
    mockApi(anonymous)
    renderApp('/verificar')
    expect(await screen.findByText('Si no lo ves, revisa la carpeta de spam.')).toBeInTheDocument()
  })
})

describe('recuperar contraseña', () => {
  it('pide el código y ofrece seguir', async () => {
    const calls = mockApi({ ...anonymous, 'POST /auth/forgot-password': { body: {} } })
    const { user } = renderApp('/recuperar')
    await user.type(await screen.findByLabelText('Correo electrónico'), 'ana@example.com')
    await user.click(screen.getByRole('button', { name: 'Enviar código' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Si el correo es válido')
    expect(screen.getByRole('link', { name: 'Ya tengo el código' })).toHaveAttribute('href', '/restablecer')
    expect(calls.find((call) => call.path === '/auth/forgot-password')?.body).toEqual({
      email: 'ana@example.com',
      language: 'es',
    })
  })

  it('cambia la contraseña y lleva a entrar con un aviso', async () => {
    const calls = mockApi({ ...anonymous, 'POST /auth/reset-password': { body: { ok: true } } })
    const { user } = renderApp('/restablecer')
    await user.type(await screen.findByLabelText('Correo electrónico'), 'ana@example.com')
    await user.click(screen.getAllByRole('textbox')[1])
    await user.keyboard('654321')
    await user.type(screen.getByLabelText('Contraseña nueva'), 'nueva-clave-segura-9')
    await user.click(screen.getByRole('button', { name: 'Cambiar contraseña' }))
    await waitFor(() => expect(pathname()).toBe('/entrar'))
    expect(await screen.findByText('Contraseña cambiada. Ya puedes entrar con la nueva.')).toBeInTheDocument()
    expect(calls.find((call) => call.path === '/auth/reset-password')?.body).toEqual({
      email: 'ana@example.com',
      code: '654321',
      new_password: 'nueva-clave-segura-9',
    })
  })

  it('un código malo no cambia de pantalla y vacía las casillas', async () => {
    mockApi({ ...anonymous, 'POST /auth/reset-password': apiError(400, 'invalid_code') })
    const { user } = renderApp('/restablecer')
    await user.type(await screen.findByLabelText('Correo electrónico'), 'ana@example.com')
    await user.click(screen.getAllByRole('textbox')[1])
    await user.keyboard('000000')
    await user.type(screen.getByLabelText('Contraseña nueva'), 'nueva-clave-segura-9')
    await user.click(screen.getByRole('button', { name: 'Cambiar contraseña' }))
    expect(await alertText()).toContain('El código no es correcto')
    expect(pathname()).toBe('/restablecer')
  })
})

describe('sesión abierta', () => {
  it('Ajustes muestra el correo y cierra la sesión', async () => {
    const calls = mockApi({
      'GET /me': { body: { user: ANA } },
      'POST /auth/logout': { body: { ok: true } },
    })
    const { user } = renderApp('/ajustes')
    expect(await screen.findByText('Has entrado como ana@example.com')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() => expect(pathname()).toBe('/bienvenida'))
    expect(calls.some((call) => call.path === '/auth/logout' && call.method === 'POST')).toBe(true)
  })

  it('aunque falle la petición de cierre, en el dispositivo se da por cerrada', async () => {
    mockApi({ 'GET /me': { body: { user: ANA } } }) // el logout no está simulado: falla
    const { user } = renderApp('/ajustes')
    await user.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() => expect(pathname()).toBe('/bienvenida'))
  })
})
