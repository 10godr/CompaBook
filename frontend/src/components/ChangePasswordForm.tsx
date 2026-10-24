import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '../api'
import { errorMessage } from '../errors'
import { PasswordField } from './TextField'

export default function ChangePasswordForm() {
  const { t } = useTranslation()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [errors, setErrors] = useState<{ current?: string; next?: string; form?: string }>({})
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setDone(false)
    const found: typeof errors = {}
    if (!current) found.current = t('auth.errors.passwordRequired')
    if (next.length < 8) found.next = t('auth.errors.passwordShort')
    setErrors(found)
    if (found.current || found.next) return

    setBusy(true)
    try {
      await api('/me/change-password', {
        method: 'POST',
        body: { current_password: current, new_password: next },
      })
      setCurrent('')
      setNext('')
      setDone(true)
    } catch (failure) {
      setErrors({ form: errorMessage(t, failure) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit} noValidate>
      <h2>{t('settings.changePassword.title')}</h2>
      {errors.form ? (
        <p className="alert alert-error" role="alert">
          {errors.form}
        </p>
      ) : null}
      {done ? (
        <p className="alert alert-success" role="status">
          {t('settings.changePassword.done')}
        </p>
      ) : null}
      <PasswordField
        label={t('settings.changePassword.current')}
        autoComplete="current-password"
        value={current}
        error={errors.current}
        onChange={(event) => setCurrent(event.target.value)}
      />
      <PasswordField
        label={t('settings.changePassword.new')}
        autoComplete="new-password"
        value={next}
        error={errors.next}
        onChange={(event) => setNext(event.target.value)}
      />
      <button type="submit" className="btn btn-secondary" disabled={busy}>
        {t('settings.changePassword.submit')}
      </button>
    </form>
  )
}
