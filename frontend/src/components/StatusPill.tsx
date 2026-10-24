import { useTranslation } from 'react-i18next'

import type { JobStatus } from '../concepts/types'

// Píldora de estado del Cuaderno (design.md §7). Un concepto completado no lleva ninguna.
export default function StatusPill({ status }: { status: JobStatus }) {
  const { t } = useTranslation()
  if (status === 'completed') return null
  return (
    <span className={`pill pill-${status}`}>
      <span className="pill-dot" aria-hidden="true" />
      {t(`status.${status}`)}
    </span>
  )
}
