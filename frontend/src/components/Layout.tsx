import { BookOpen, Home, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet } from 'react-router-dom'

export default function Layout() {
  const { t } = useTranslation()

  return (
    <div className="app">
      <nav className="nav" aria-label={t('nav.label')}>
        <span className="nav-brand">CompaBook</span>
        <NavLink to="/" end className="nav-link">
          <Home aria-hidden="true" />
          {t('nav.home')}
        </NavLink>
        <NavLink to="/cuaderno" className="nav-link">
          <BookOpen aria-hidden="true" />
          {t('nav.notebook')}
        </NavLink>
        <NavLink to="/ajustes" className="nav-link">
          <Settings aria-hidden="true" />
          {t('nav.settings')}
        </NavLink>
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
