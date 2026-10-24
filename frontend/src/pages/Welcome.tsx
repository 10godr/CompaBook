import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

export default function Welcome() {
  const { t } = useTranslation()

  return (
    <div className="welcome">
      <h1 className="display">
        {t('welcome.titleLine1')}
        <br />
        <span className="headline-muted">{t('welcome.titleLine2')}</span>
      </h1>
      <div className="stack">
        <Link to="/registro" className="btn btn-primary">
          {t('welcome.register')}
        </Link>
        <Link to="/entrar" className="btn btn-outline">
          {t('welcome.login')}
        </Link>
      </div>
      {/* Temporal (Fase 4): la app instalada no tiene barra de direcciones y las pruebas
          de cookie y push se hacen sin sesión. Se quitan al cerrar la fase. */}
      <div className="stack stack-small">
        <Link to="/prueba-cookie" className="link">
          Prueba de cookie
        </Link>
        <Link to="/prueba-push" className="link">
          Prueba de push
        </Link>
      </div>
    </div>
  )
}
