import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '../auth/context'
import { type Language, setLanguage } from '../i18n'
import { getThemePreference, setThemePreference, type ThemePreference } from '../theme'

const LANGUAGES: Language[] = ['es', 'en']
const THEMES: ThemePreference[] = ['system', 'dark', 'light']

export default function Settings() {
  const { t, i18n } = useTranslation()
  const { user, logout } = useAuth()
  const [theme, setTheme] = useState(getThemePreference)

  return (
    <>
      <h1>{t('settings.title')}</h1>

      <div className="card">
        <label className="field-label" htmlFor="language">
          {t('settings.language')}
        </label>
        <select
          id="language"
          className="select"
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

      <div className="card">
        <h2>{t('settings.session')}</h2>
        <p className="muted">{t('settings.signedInAs', { email: user?.email })}</p>
        <button type="button" className="btn btn-outline" onClick={() => void logout()}>
          {t('settings.logout')}
        </button>
      </div>

      <div className="card">
        <label className="field-label" htmlFor="theme">
          {t('settings.theme')}
        </label>
        <select
          id="theme"
          className="select"
          value={theme}
          onChange={(event) => {
            const preference = event.target.value as ThemePreference
            setThemePreference(preference)
            setTheme(preference)
          }}
        >
          {THEMES.map((preference) => (
            <option key={preference} value={preference}>
              {t(`settings.themeOptions.${preference}`)}
            </option>
          ))}
        </select>
      </div>
    </>
  )
}
