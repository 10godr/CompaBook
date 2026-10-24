import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import AddConcept from '../components/AddConcept'
import ConceptRow from '../components/ConceptRow'
import { useConceptList } from '../concepts/useConceptList'
import { useUsage } from '../concepts/useUsage'

const RECENT = 5

export default function Home() {
  const { t } = useTranslation()
  const { usage, refresh } = useUsage()
  const recent = useConceptList('', RECENT)

  return (
    <>
      <h1>
        {t('home.titleLine1')}
        <br />
        <span className="headline-muted">{t('home.titleLine2')}</span>
      </h1>

      <AddConcept usage={usage} onLimitReached={() => void refresh()} />

      <section className="stack" aria-labelledby="recent-title">
        <h2 id="recent-title">{t('home.recent')}</h2>
        {recent.status === 'error' ? (
          <p className="alert alert-error" role="alert">
            {t('notebook.loadError')}{' '}
            <button type="button" className="link-button" onClick={() => void recent.reload()}>
              {t('notebook.retry')}
            </button>
          </p>
        ) : recent.items.length > 0 ? (
          <>
            <ul className="concept-list">
              {recent.items.map((concept) => (
                <ConceptRow key={concept.id} concept={concept} />
              ))}
            </ul>
            <Link to="/cuaderno" className="link">
              {t('home.seeAll')}
            </Link>
          </>
        ) : recent.status === 'ready' ? (
          <p className="muted">{t('home.emptyRecent')}</p>
        ) : null}
      </section>

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
