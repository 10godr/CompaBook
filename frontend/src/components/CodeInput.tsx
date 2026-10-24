import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

const LENGTH = 6

interface Props {
  value: string
  onChange: (value: string) => void
  label: string
  disabled?: boolean
  error?: boolean
}

// Seis casillas de un dígito. Admite escribir, pegar el código entero y el autocompletado de iOS
// (`autocomplete="one-time-code"`), que llega como los seis dígitos juntos en la primera casilla.
export default function CodeInput({ value, onChange, label, disabled, error }: Props) {
  const { t } = useTranslation()
  const boxes = useRef<(HTMLInputElement | null)[]>([])
  const pendingFocus = useRef<number | null>(null)

  function focusBox(index: number) {
    boxes.current[Math.min(Math.max(index, 0), LENGTH - 1)]?.focus()
  }

  // El foco se mueve DESPUÉS de pintar el valor nuevo: si se moviera antes, `onFocus` vería el
  // valor viejo y devolvería el foco a la primera casilla libre antigua.
  useEffect(() => {
    if (pendingFocus.current === null) return
    focusBox(pendingFocus.current)
    pendingFocus.current = null
  })

  function update(next: string) {
    pendingFocus.current = next.length
    onChange(next)
  }

  function handleChange(index: number, raw: string) {
    const digits = raw.replace(/\D/g, '')
    if (digits === '') return update(value.slice(0, index))
    // Escribir encima de una casilla llena deja dos dígitos: se queda el nuevo, que es el último.
    const typedOverFilledBox = digits.length === 2 && value[index] !== undefined
    // Varios dígitos de golpe (autocompletado o pegado en una casilla): se reparten desde el principio.
    if (digits.length > 1 && !typedOverFilledBox) return update(digits.slice(0, LENGTH))
    const digit = digits.slice(-1)
    update((value.slice(0, index) + digit + value.slice(index + 1)).slice(0, LENGTH))
  }

  function handleKeyDown(index: number, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Backspace' && !value[index] && value.length > 0) {
      event.preventDefault()
      update(value.slice(0, -1))
    } else if (event.key === 'ArrowLeft') {
      focusBox(index - 1)
    } else if (event.key === 'ArrowRight') {
      focusBox(index + 1)
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const digits = event.clipboardData.getData('text').replace(/\D/g, '')
    if (!digits) return
    event.preventDefault()
    update(digits.slice(0, LENGTH))
  }

  return (
    <div className="code-input" role="group" aria-label={label}>
      {Array.from({ length: LENGTH }, (_, index) => (
        <input
          key={index}
          ref={(element) => {
            boxes.current[index] = element
          }}
          className="code-box"
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="one-time-code"
          aria-label={t('auth.verify.digit', { n: index + 1 })}
          aria-invalid={error ? true : undefined}
          value={value[index] ?? ''}
          disabled={disabled}
          // Si se toca una casilla más allá de la siguiente libre, el foco va a la siguiente libre.
          onFocus={() => index > value.length && focusBox(value.length)}
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={handlePaste}
        />
      ))}
    </div>
  )
}
