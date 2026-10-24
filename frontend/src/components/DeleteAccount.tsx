import { useCallback, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '../api'
import { useAuth } from '../auth/context'
import { errorMessage } from '../errors'
import ConfirmDialog from './ConfirmDialog'
import { PasswordField } from './TextField'

export default function DeleteAccount() {
  const { t } = useTranslation()
  const { clearSession } = useAuth()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const close = useCallback(() => {
    setOpen(false)
    setPassword('')
    setError('')
  }, [])

  async function confirm(event: FormEvent) {
    event.preventDefault()
    if (!password) return setError(t('auth.errors.passwordRequired'))
    setError('')
    setBusy(true)
    try {
      await api('/me', { method: 'DELETE', body: { password } })
      // La cuenta ya no existe: se sale sin llamar a logout. La guarda lleva a la bienvenida.
      clearSession()
    } catch (failure) {
      setError(errorMessage(t, failure))
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <h2>{t('settings.deleteAccount.title')}</h2>
      <p className="muted">{t('settings.deleteAccount.description')}</p>
      <button type="button" className="btn btn-danger" onClick={() => setOpen(true)}>
        {t('settings.deleteAccount.button')}
      </button>

      {open ? (
        <ConfirmDialog title={t('settings.deleteAccount.confirmTitle')} onClose={close}>
          <form className="auth-form" onSubmit={confirm} noValidate>
            <p className="muted">{t('settings.deleteAccount.confirmText')}</p>
            {error ? (
              <p className="alert alert-error" role="alert">
                {error}
              </p>
            ) : null}
            <PasswordField
              label={t('auth.password')}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button type="submit" className="btn btn-danger" disabled={busy}>
              {t('settings.deleteAccount.confirm')}
            </button>
            <button type="button" className="btn btn-secondary" onClick={close} disabled={busy}>
              {t('settings.deleteAccount.cancel')}
            </button>
          </form>
        </ConfirmDialog>
      ) : null}
    </div>
  )
}
