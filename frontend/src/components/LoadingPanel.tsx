import { useTranslation } from 'react-i18next'

import type { JobStage } from '../concepts/types'

const STAGES = ['queued', 'writing', 'finding_videos', 'done'] as const

interface Props {
  stage: JobStage
  /** Intentos que ya fallaron: con alguno y de vuelta en cola, el trabajo se está reintentando. */
  attempts: number
  /** Lleva más de 3 minutos sin terminar: se deja de preguntar y se avisa. */
  slow: boolean
}

// Ocupa el lugar de la ficha mientras se genera: barra de etapas, el paso actual en texto y un
// esqueleto con la forma de la ficha (design.md §7).
export default function LoadingPanel({ stage, attempts, slow }: Props) {
  const { t } = useTranslation()
  const currentIndex = STAGES.indexOf(stage)
  const retrying = stage === 'queued' && attempts > 0

  return (
    <section className="panel" aria-busy="true">
      <ol className="stages" aria-label={t('concept.progress.label')}>
        {STAGES.map((name, index) => {
          const state = index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'todo'
          return (
            <li key={name} className={`stage stage-${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="stage-name">{t(`concept.stages.${name}`)}</span>
            </li>
          )
        })}
      </ol>
      <p className="panel-text" aria-live="polite">
        {retrying ? t('concept.progress.retrying') : t(`concept.progress.${stage}`)}
      </p>
      {slow ? <p className="alert alert-warning">{t('concept.slow')}</p> : null}
      <div className="skeleton" aria-hidden="true">
        <div className="skeleton-line skeleton-title" />
        <div className="skeleton-line" />
        <div className="skeleton-line" />
        <div className="skeleton-line skeleton-short" />
      </div>
    </section>
  )
}
