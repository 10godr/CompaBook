import { AlertCircle, ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import CardView from '../components/CardView'
import LoadingPanel from '../components/LoadingPanel'
import { isActive } from '../concepts/types'
import { useConcept } from '../concepts/useConcept'
import { errorMessage } from '../errors'

// `key={id}`: al pasar de un concepto a otro, la pantalla se monta de nuevo y parte de cero.
export default function ConceptPage() {
  const { id = '' } = useParams()
  return <ConceptView key={id} id={id} />
}

function ConceptView({ id }: { id: string }) {
  const { t } = useTranslation()
  const { concept, phase, slow, retry, reload } = useConcept(id)
  const [retryError, setRetryError] = useState('')
  const [retrying, setRetrying] = useState(false)

  async function onRetry() {
    setRetryError('')
    setRetrying(true)
    try {
      await retry()
    } catch (failure) {
      setRetryError(errorMessage(t, failure))
    }
    setRetrying(false)
  }

  const back = (
    <Link to="/cuaderno" className="back-link">
      <ArrowLeft aria-hidden="true" />
      {t('concept.back')}
    </Link>
  )

  if (phase === 'loading') {
    return (
      <>
        {back}
        <p className="muted">{t('common.loading')}</p>
      </>
    )
  }

  if (phase === 'error' && !concept) {
    return (
      <>
        {back}
        <p className="alert alert-error" role="alert">
          {t('notebook.loadError')}{' '}
          <button type="button" className="link-button" onClick={reload}>
            {t('notebook.retry')}
          </button>
        </p>
      </>
    )
  }

  if (phase === 'missing' || !concept) {
    return (
      <>
        {back}
        <p className="muted">{t('concept.notFound')}</p>
      </>
    )
  }

  return (
    <>
      {back}
      {isActive(concept.status) ? <LoadingPanel stage={concept.stage} slow={slow} /> : null}

      {concept.status === 'failed' ? (
        <section className="panel panel-error">
          <AlertCircle aria-hidden="true" className="panel-icon" />
          <h1 className="panel-title">{t('concept.failed')}</h1>
          <p className="muted">{t('concept.failedHelp')}</p>
          {retryError ? (
            <p className="alert alert-error" role="alert">
              {retryError}
            </p>
          ) : null}
          <button type="button" className="btn btn-primary" onClick={() => void onRetry()} disabled={retrying}>
            {t('concept.retry')}
          </button>
        </section>
      ) : null}

      {concept.status === 'completed' ? (
        concept.card ? (
          <CardView concept={concept} />
        ) : (
          <p className="muted">{t('concept.noCard')}</p>
        )
      ) : null}
    </>
  )
}
