import { Search } from 'lucide-react'
import { useCallback, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { api, ApiError } from '../api'
import ConceptMenu from '../components/ConceptMenu'
import ConceptRow from '../components/ConceptRow'
import ConfirmDialog from '../components/ConfirmDialog'
import Toast from '../components/Toast'
import type { ConceptSummary } from '../concepts/types'
import { useConceptList } from '../concepts/useConceptList'
import { errorMessage } from '../errors'
import { useDebounced } from '../useDebounced'

const PAGE_SIZE = 20
const SEARCH_DELAY_MS = 300

export default function Notebook() {
  const { t } = useTranslation()
  const searchId = useId()
  const [text, setText] = useState('')
  const query = useDebounced(text.trim(), SEARCH_DELAY_MS)
  const list = useConceptList(query, PAGE_SIZE)

  const [pending, setPending] = useState<ConceptSummary | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [toast, setToast] = useState('')
  const closeToast = useCallback(() => setToast(''), [])

  const closeDialog = useCallback(() => {
    setPending(null)
    setDeleteError('')
  }, [])

  async function confirmDelete() {
    if (!pending) return
    setDeleting(true)
    setDeleteError('')
    try {
      await api(`/concepts/${pending.id}`, { method: 'DELETE' })
    } catch (failure) {
      // Si ya no existía, el resultado es el que se quería: se quita de la lista igualmente.
      if (!(failure instanceof ApiError && failure.status === 404)) {
        setDeleteError(errorMessage(t, failure))
        setDeleting(false)
        return
      }
    }
    list.remove(pending.id)
    setDeleting(false)
    closeDialog()
    setToast(t('notebook.deleted'))
  }

  const searching = query !== ''
  const isEmpty = list.status === 'ready' && list.items.length === 0

  return (
    <>
      <h1>{t('notebook.title')}</h1>

      <div className="field">
        <label className="field-label" htmlFor={searchId}>
          {t('notebook.search')}
        </label>
        <div className="input-wrap search-wrap">
          <Search aria-hidden="true" className="search-icon" />
          <input
            id={searchId}
            type="search"
            className="input search-input"
            value={text}
            maxLength={200}
            autoComplete="off"
            onChange={(event) => setText(event.target.value)}
          />
        </div>
      </div>

      {list.status === 'error' ? (
        <p className="alert alert-error" role="alert">
          {t('notebook.loadError')}{' '}
          <button type="button" className="link-button" onClick={() => void list.reload()}>
            {t('notebook.retry')}
          </button>
        </p>
      ) : null}

      {list.status === 'loading' && list.items.length === 0 ? <p className="muted">{t('common.loading')}</p> : null}

      {isEmpty && searching ? <p className="muted">{t('notebook.noResults', { query })}</p> : null}

      {isEmpty && !searching ? (
        <div className="empty">
          <h2 className="empty-title">
            {t('notebook.emptyTitle1')}
            <br />
            <span className="headline-muted">{t('notebook.emptyTitle2')}</span>
          </h2>
          <Link to="/" className="btn btn-primary">
            {t('notebook.emptyAction')}
          </Link>
        </div>
      ) : null}

      {list.items.length > 0 ? (
        <ul className="concept-list" aria-busy={list.status === 'loading'}>
          {list.items.map((concept) => (
            <ConceptRow
              key={concept.id}
              concept={concept}
              actions={<ConceptMenu title={concept.title} onDelete={() => setPending(concept)} />}
            />
          ))}
        </ul>
      ) : null}

      {list.loadMoreFailed ? (
        <p className="alert alert-error" role="alert">
          {t('notebook.loadError')}
        </p>
      ) : null}
      {list.hasMore ? (
        <button type="button" className="btn btn-secondary" onClick={() => void list.loadMore()} disabled={list.loadingMore}>
          {t('notebook.loadMore')}
        </button>
      ) : null}

      {pending ? (
        <ConfirmDialog title={t('notebook.deleteTitle')} onClose={closeDialog}>
          <p className="muted">{t('notebook.deleteText', { title: pending.title })}</p>
          {deleteError ? (
            <p className="alert alert-error" role="alert">
              {deleteError}
            </p>
          ) : null}
          <button type="button" className="btn btn-danger" onClick={() => void confirmDelete()} disabled={deleting}>
            {t('notebook.confirmDelete')}
          </button>
          <button type="button" className="btn btn-secondary" onClick={closeDialog} disabled={deleting}>
            {t('notebook.cancel')}
          </button>
        </ConfirmDialog>
      ) : null}

      {toast ? <Toast message={toast} onClose={closeToast} /> : null}
    </>
  )
}
