import { useTranslation } from 'react-i18next'

export default function Home() {
  const { t } = useTranslation()

  return (
    <h1>
      {t('home.titleLine1')}
      <br />
      <span className="headline-muted">{t('home.titleLine2')}</span>
    </h1>
  )
}
