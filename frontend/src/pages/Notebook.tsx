import { useTranslation } from 'react-i18next'

export default function Notebook() {
  const { t } = useTranslation()

  return <h1>{t('notebook.title')}</h1>
}
