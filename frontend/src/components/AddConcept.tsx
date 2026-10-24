import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { api, ApiError } from '../api'
import type { Usage } from '../concepts/types'
import { errorMessage } from '../errors'

const TITLE_MAX = 200
// El contador «n/200» solo aparece cuando ya se acerca al tope.
const COUNTER_FROM = 160

interface Props {
  usage: Usage | null
  /** La API dijo que se llegó al límite: hay que volver a leer el uso del día. */
  onLimitReached: () => void
}

// Campo para añadir un concepto (design.md §7). Al guardarlo se abre su ficha, que es la que
// pone en marcha la generación y muestra el panel de carga.
export default function AddConcept({ usage, onLimitReached }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const inputId = useId()
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const limitReached = usage !== null && usage.concepts_today >= usage.daily_limit
  const title = text.trim()

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!title || busy || limitReached) return
    setError('')
    setBusy(true)
    try {
      const created = await api<{ id: string }>('/concepts', { method: 'POST', body: { title } })
      navigate(`/cuaderno/${created.id}`)
    } catch (failure) {
      setError(errorMessage(t, failure))
      if (failure instanceof ApiError && failure.code === 'daily_limit_reached') onLimitReached()
      setBusy(false)
    }
  }

  return (
    <form className="add-form" onSubmit={submit} noValidate>
      <label className="field-label" htmlFor={inputId}>
        {t('home.add.label')}
      </label>
      <div className="add-row">
        <input
          id={inputId}
          className="input input-lg"
          value={text}
          maxLength={TITLE_MAX}
          placeholder={t('home.add.placeholder')}
          autoComplete="off"
          enterKeyHint="send"
          onChange={(event) => setText(event.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={!title || busy || limitReached}>
          {t('home.add.submit')}
        </button>
      </div>
      {text.length >= COUNTER_FROM ? (
        <p className="hint add-counter">
          {text.length}/{TITLE_MAX}
        </p>
      ) : null}
      {error ? (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      ) : null}
      {usage ? (
        <p className="hint">
          {limitReached
            ? t('home.add.limitReached')
            : t('home.add.usage', { used: usage.concepts_today, limit: usage.daily_limit })}
        </p>
      ) : null}
    </form>
  )
}
