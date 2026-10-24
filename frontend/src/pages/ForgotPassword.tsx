import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { api } from '../api'
import { TextField } from '../components/TextField'
import { errorMessage, isEmail } from '../errors'

export default function ForgotPassword() {
  const { t, i18n } = useTranslation()
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!isEmail(email)) return setError(t('auth.errors.emailInvalid'))
    setError('')
    setBusy(true)
    try {
      await api('/auth/forgot-password', {
        method: 'POST',
        body: { email: email.trim(), language: i18n.language },
      })
      setSent(true)
    } catch (failure) {
      setError(errorMessage(t, failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="auth-form" onSubmit={submit} noValidate>
      <h1>{t('auth.forgot.title')}</h1>
      <p className="muted">{t('auth.forgot.intro')}</p>
      {error ? (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      ) : null}
      {sent ? (
        <>
          <p className="alert alert-success" role="status">
            {t('auth.forgot.sent')}
          </p>
          <Link to="/restablecer" state={{ email: email.trim() }} className="btn btn-primary">
            {t('auth.forgot.haveCode')}
          </Link>
        </>
      ) : null}
      <TextField
        label={t('auth.email')}
        type="email"
        autoComplete="email"
        inputMode="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <button type="submit" className={sent ? 'btn btn-secondary' : 'btn btn-primary'} disabled={busy}>
        {t('auth.forgot.submit')}
      </button>
      <Link to="/entrar" className="link">
        {t('auth.back')}
      </Link>
    </form>
  )
}
