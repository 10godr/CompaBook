import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'

import { api } from '../api'
import { useAuth, type User } from '../auth/context'
import CodeInput from '../components/CodeInput'
import { TextField } from '../components/TextField'
import { errorMessage, isEmail } from '../errors'

const RESEND_COOLDOWN_SECONDS = 60

export default function Verify() {
  const { t, i18n } = useTranslation()
  const { setUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const knownEmail = (location.state as { email?: string } | null)?.email
  const [email, setEmail] = useState(knownEmail ?? '')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [busy, setBusy] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setTimeout(() => setCooldown((seconds) => seconds - 1), 1000)
    return () => clearTimeout(timer)
  }, [cooldown])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setInfo('')
    if (!isEmail(email)) return setError(t('auth.errors.emailInvalid'))
    if (code.length !== 6) return setError(t('auth.errors.codeIncomplete'))

    setError('')
    setBusy(true)
    try {
      const data = await api<{ user: User }>('/auth/verify-email', {
        method: 'POST',
        body: { email: email.trim(), code },
      })
      setUser(data.user)
      navigate('/', { replace: true })
    } catch (failure) {
      setError(errorMessage(t, failure))
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    setInfo('')
    if (!isEmail(email)) return setError(t('auth.errors.emailInvalid'))
    setError('')
    try {
      await api('/auth/resend-code', {
        method: 'POST',
        body: { email: email.trim(), purpose: 'verify_email', language: i18n.language },
      })
      setInfo(t('auth.verify.resent'))
      setCooldown(RESEND_COOLDOWN_SECONDS)
    } catch (failure) {
      setError(errorMessage(t, failure))
    }
  }

  return (
    <form className="auth-form" onSubmit={submit} noValidate>
      <h1>{t('auth.verify.title')}</h1>
      <p className="muted">
        {knownEmail ? t('auth.verify.intro', { email: knownEmail }) : t('auth.verify.introNoEmail')}
      </p>
      {error ? (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      ) : null}
      {info ? (
        <p className="alert alert-success" role="status">
          {info}
        </p>
      ) : null}
      {knownEmail ? null : (
        <TextField
          label={t('auth.email')}
          type="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      )}
      <CodeInput value={code} onChange={setCode} label={t('auth.verify.code')} disabled={busy} error={!!error} />
      <p className="hint">{t('auth.verify.spam')}</p>
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {t('auth.verify.submit')}
      </button>
      <button type="button" className="btn btn-secondary" disabled={cooldown > 0} onClick={resend}>
        {cooldown > 0 ? t('auth.verify.resendIn', { seconds: cooldown }) : t('auth.verify.resend')}
      </button>
    </form>
  )
}
