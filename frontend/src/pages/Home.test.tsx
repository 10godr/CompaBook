import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ANA, mockApi } from '../test/mockApi'
import { renderApp } from '../test/render'

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
