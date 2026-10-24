import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/context'
import { formatDate } from '../concepts/format'
import type { ConceptSummary } from '../concepts/types'
import StatusPill from './StatusPill'

interface Props {
  concept: ConceptSummary
  /** Botones propios de la lista (p. ej. el menú de eliminar); van fuera del enlace. */
  actions?: ReactNode
}

// Tarjeta de un concepto en el Cuaderno y en Inicio. Todo el cuerpo es un enlace a la ficha.
export default function ConceptRow({ concept, actions }: Props) {
  const { i18n } = useTranslation()
  const { user } = useAuth()

  return (
    <li className="concept-row">
      <Link to={`/cuaderno/${concept.id}`} className="concept-link">
        <span className="concept-main">
          {/* Lo que escribió el usuario, siempre como texto. */}
          <span className="concept-title">{concept.title}</span>
          <span className="concept-date">{formatDate(concept.created_at, i18n.language, user?.timezone)}</span>
        </span>
        <StatusPill status={concept.status} />
      </Link>
      {actions}
    </li>
  )
}
