import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { api } from '../api'
import CodeInput from '../components/CodeInput'
import { PasswordField, TextField } from '../components/TextField'
import { errorMessage, isEmail } from '../errors'

export default function ResetPassword() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const knownEmail = (location.state as { email?: string } | null)?.email
  const [email, setEmail] = useState(knownEmail ?? '')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ email?: string; password?: string; form?: string }>({})
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const next: typeof errors = {}
    if (!isEmail(email)) next.email = t('auth.errors.emailInvalid')
    if (password.length < 8) next.password = t('auth.errors.passwordShort')
    if (code.length !== 6) next.form = t('auth.errors.codeIncomplete')
    setErrors(next)
    if (next.email || next.password || next.form) return

    setBusy(true)
    try {
      await api('/auth/reset-password', {
        method: 'POST',
        body: { email: email.trim(), code, new_password: password },
      })
      navigate('/entrar', { replace: true, state: { passwordReset: true } })
    } catch (failure) {
      setErrors({ form: errorMessage(t, failure) })
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="auth-form" onSubmit={submit} noValidate>
      <h1>{t('auth.reset.title')}</h1>
      <p className="muted">{t('auth.reset.intro')}</p>
      {errors.form ? (
        <p className="alert alert-error" role="alert">
          {errors.form}
        </p>
      ) : null}
      {knownEmail ? null : (
        <TextField
          label={t('auth.email')}
          type="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          error={errors.email}
          onChange={(event) => setEmail(event.target.value)}
        />
      )}
      <CodeInput value={code} onChange={setCode} label={t('auth.verify.code')} disabled={busy} error={!!errors.form} />
      <PasswordField
        label={t('auth.newPassword')}
        autoComplete="new-password"
        value={password}
        error={errors.password}
        onChange={(event) => setPassword(event.target.value)}
      />
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {t('auth.reset.submit')}
      </button>
      <Link to="/recuperar" className="link">
        {t('auth.back')}
      </Link>
    </form>
  )
}
