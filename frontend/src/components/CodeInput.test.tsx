import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'

import CodeInput from './CodeInput'

function Harness({ initial = '' }: { initial?: string }) {
  const [value, setValue] = useState(initial)
  return (
    <>
      <CodeInput value={value} onChange={setValue} label="Código" />
      <output data-testid="value">{value}</output>
    </>
  )
}

const boxes = () => screen.getAllByRole('textbox') as HTMLInputElement[]
const value = () => screen.getByTestId('value').textContent

describe('CodeInput', () => {
  it('tiene seis casillas numéricas con su etiqueta y el autocompletado del código por correo', () => {
    render(<Harness />)
    expect(screen.getByRole('group', { name: 'Código' })).toBeInTheDocument()
    expect(boxes()).toHaveLength(6)
    expect(boxes()[0]).toHaveAttribute('inputmode', 'numeric')
    expect(boxes()[0]).toHaveAttribute('autocomplete', 'one-time-code')
    expect(boxes()[2]).toHaveAccessibleName('Dígito 3 de 6')
  })

  it('al escribir, el foco avanza a la siguiente casilla', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(boxes()[0])
    await user.keyboard('123')
    expect(value()).toBe('123')
    expect(boxes()[3]).toHaveFocus()
    expect(boxes().map((box) => box.value).join('')).toBe('123')
  })

  it('admite seis dígitos y no más: el séptimo sustituye al último, no alarga el código', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(boxes()[0])
    await user.keyboard('1234567')
    expect(value()).toHaveLength(6)
    expect(value()?.startsWith('12345')).toBe(true)
  })

  it('escribir encima de una casilla llena la sustituye', async () => {
    const user = userEvent.setup()
    render(<Harness initial="123456" />)
    await user.click(boxes()[2])
    await user.keyboard('9')
    expect(value()).toBe('129456')
  })

  it('ignora lo que no son dígitos', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(boxes()[0])
    await user.keyboard('a1-b2')
    expect(value()).toBe('12')
  })

  it('pegar el código entero rellena todas las casillas', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(boxes()[0])
    await user.paste('482 913')
    expect(value()).toBe('482913')
    expect(boxes()[5]).toHaveFocus()
  })

  it('pegar texto sin dígitos no cambia nada', async () => {
    const user = userEvent.setup()
    render(<Harness initial="12" />)
    await user.click(boxes()[2])
    await user.paste('abc')
    expect(value()).toBe('12')
  })

  it('el autocompletado de iOS llega como los seis dígitos de golpe en la primera casilla', () => {
    render(<Harness />)
    fireEvent.change(boxes()[0], { target: { value: '654321' } })
    expect(value()).toBe('654321')
    expect(boxes().map((box) => box.value).join('')).toBe('654321')
  })

  it('borrar con retroceso quita el último dígito y vuelve a la casilla anterior', async () => {
    const user = userEvent.setup()
    render(<Harness initial="123" />)
    await user.click(boxes()[3])
    await user.keyboard('{Backspace}')
    expect(value()).toBe('12')
    expect(boxes()[2]).toHaveFocus()
  })

  it('tocar una casilla más allá de la siguiente libre manda el foco a la libre', async () => {
    const user = userEvent.setup()
    render(<Harness initial="12" />)
    await user.click(boxes()[5])
    expect(boxes()[2]).toHaveFocus()
  })

  it('con las flechas se mueve entre casillas', async () => {
    const user = userEvent.setup()
    render(<Harness initial="123456" />)
    await user.click(boxes()[3])
    await user.keyboard('{ArrowLeft}')
    expect(boxes()[2]).toHaveFocus()
    await user.keyboard('{ArrowRight}{ArrowRight}')
    expect(boxes()[4]).toHaveFocus()
  })
})
