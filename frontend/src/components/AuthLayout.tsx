import { useTranslation } from 'react-i18next'
import { Link, Outlet } from 'react-router-dom'

import { type Language, setLanguage } from '../i18n'

const LANGUAGES: Language[] = ['es', 'en']

// Marco de las pantallas sin sesión: marca, selector de idioma visible y contenido centrado.
export default function AuthLayout() {
  const { t, i18n } = useTranslation()

  return (
    <div className="auth-page">
      <header className="auth-header">
        <Link to="/bienvenida" className="brand">
          CompaBook
        </Link>
        <div>
          <label className="visually-hidden" htmlFor="interface-language">
            {t('auth.interfaceLanguage')}
          </label>
          <select
            id="interface-language"
            className="select select-small"
            value={i18n.language}
            onChange={(event) => setLanguage(event.target.value as Language)}
          >
            {LANGUAGES.map((language) => (
              <option key={language} value={language}>
                {t(`languages.${language}`)}
              </option>
            ))}
          </select>
        </div>
      </header>
      <main className="auth-main">
        <Outlet />
      </main>
    </div>
  )
}
