import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api'
import { PasswordField, TextField } from '../components/TextField'
import { errorMessage, isEmail } from '../errors'
import { type Language, setLanguage } from '../i18n'

const LANGUAGES: Language[] = ['es', 'en']

export default function Register() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [accepted, setAccepted] = useState(false)
  const [errors, setErrors] = useState<{
    email?: string
    password?: string
    terms?: string
    form?: string
  }>({})
  const [busy, setBusy] = useState(false)
  const language = i18n.language as Language

  async function submit(event: FormEvent) {
    event.preventDefault()
    const next: typeof errors = {}
    if (!isEmail(email)) next.email = t('auth.errors.emailInvalid')
    if (password.length < 8) next.password = t('auth.errors.passwordShort')
    if (!accepted) next.terms = t('auth.errors.termsRequired')
    setErrors(next)
    if (next.email || next.password || next.terms) return

    setBusy(true)
    try {
      await api('/auth/register', {
        method: 'POST',
        body: {
          email: email.trim(),
          password,
          language,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          accept_terms: true,
        },
      })
      navigate('/verificar', { state: { email: email.trim() } })
    } catch (error) {
      setErrors({ form: errorMessage(t, error) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="auth-form" onSubmit={submit} noValidate>
      <h1>{t('auth.register.title')}</h1>
      <p className="muted">{t('auth.register.intro')}</p>
      {errors.form ? (
        <p className="alert alert-error" role="alert">
          {errors.form}
        </p>
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
        autoComplete="new-password"
        value={password}
        error={errors.password}
        onChange={(event) => setPassword(event.target.value)}
      />
      <div className="field">
        <label className="field-label" htmlFor="register-language">
          {t('auth.language')}
        </label>
        <select
          id="register-language"
          className="select"
          value={language}
          onChange={(event) => setLanguage(event.target.value as Language)}
        >
          {LANGUAGES.map((option) => (
            <option key={option} value={option}>
              {t(`languages.${option}`)}
            </option>
          ))}
        </select>
        <p className="hint">{t('auth.languageNote')}</p>
      </div>
      <div className="field">
        <label className="check">
          <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
          <span>{t('auth.terms')}</span>
        </label>
        {errors.terms ? (
          <p className="field-error" role="alert">
            {errors.terms}
          </p>
        ) : null}
      </div>
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {t('auth.register.submit')}
      </button>
      <p className="muted">
        {t('auth.register.haveAccount')}{' '}
        <Link to="/entrar" className="link">
          {t('auth.register.login')}
        </Link>
      </p>
    </form>
  )
}
