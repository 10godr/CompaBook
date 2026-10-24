import { useTranslation } from 'react-i18next'

import type { JobStage } from '../concepts/types'

// En la 6a no hay búsqueda de videos: la barra solo tiene los pasos que existen. La 6b añade
// `finding_videos` aquí y su texto en los idiomas.
const STAGES = ['queued', 'writing', 'done'] as const
type Shown = (typeof STAGES)[number]

function shownStage(stage: JobStage): Shown {
  return stage === 'finding_videos' ? 'writing' : stage
}

interface Props {
  stage: JobStage
  /** Lleva más de 3 minutos sin terminar: se deja de preguntar y se avisa. */
  slow: boolean
}

// Ocupa el lugar de la ficha mientras se genera: barra de etapas, el paso actual en texto y un
// esqueleto con la forma de la ficha (design.md §7).
export default function LoadingPanel({ stage, slow }: Props) {
  const { t } = useTranslation()
  const current = shownStage(stage)
  const currentIndex = STAGES.indexOf(current)

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
        {t(`concept.progress.${current}`)}
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
