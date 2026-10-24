import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../api'
import { useAuth } from '../auth/context'
import { PasswordField, TextField } from '../components/TextField'
import { errorMessage, isEmail } from '../errors'

export default function Login() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const notice = (location.state as { passwordReset?: boolean } | null)?.passwordReset
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ email?: string; password?: string; form?: string }>({})
  const [unverified, setUnverified] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const next: typeof errors = {}
    if (!isEmail(email)) next.email = t('auth.errors.emailInvalid')
    if (!password) next.password = t('auth.errors.passwordRequired')
    setErrors(next)
    setUnverified(false)
    if (next.email || next.password) return

    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate('/', { replace: true })
    } catch (error) {
      if (error instanceof ApiError && error.code === 'email_not_verified') setUnverified(true)
      setErrors({ form: errorMessage(t, error) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="auth-form" onSubmit={submit} noValidate>
      <h1>{t('auth.login.title')}</h1>
      {notice ? <p className="alert alert-success">{t('auth.login.passwordReset')}</p> : null}
      {errors.form ? (
        <p className="alert alert-error" role="alert">
          {errors.form}
        </p>
      ) : null}
      {unverified ? (
        <Link to="/verificar" state={{ email: email.trim() }} className="btn btn-secondary">
          {t('auth.errors.verifyNow')}
        </Link>
      ) : null}
      <TextField
        label={t('auth.email')}
        type="email"
        autoComplete="email"
        inputMode="email"
        value={email}
        error={errors.email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <PasswordField
        label={t('auth.password')}
        autoComplete="current-password"
        value={password}
        error={errors.password}
        onChange={(event) => setPassword(event.target.value)}
      />
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {t('auth.login.submit')}
      </button>
      <Link to="/recuperar" className="link">
        {t('auth.login.forgot')}
      </Link>
      <p className="muted">
        {t('auth.login.noAccount')}{' '}
        <Link to="/registro" className="link">
          {t('auth.login.register')}
        </Link>
      </p>
    </form>
  )
}
