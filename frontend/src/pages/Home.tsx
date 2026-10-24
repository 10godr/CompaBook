import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

export default function Home() {
  const { t } = useTranslation()

  return (
    <>
      <h1>
        {t('home.titleLine1')}
        <br />
        <span className="headline-muted">{t('home.titleLine2')}</span>
      </h1>
      {/* Temporal (Fase 4): la app instalada no tiene barra de direcciones. Se quitan al cerrar
          la fase, junto con los de la bienvenida. */}
      <Link to="/prueba-cookie" className="poc-link">
        Prueba de cookie
      </Link>
      <Link to="/prueba-push" className="poc-link">
        Prueba de push
      </Link>
    </>
  )
}
