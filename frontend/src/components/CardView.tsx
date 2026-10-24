import { Check, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { ConceptDetail } from '../concepts/types'

function CodeBlock({ code, language }: { code: string; language: string | null }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
    } catch {
      // Sin permiso del navegador no hay nada que hacer: el código sigue a la vista para copiarlo.
    }
  }

  return (
    <div className="code-block">
      <div className="code-head">
        <span className="code-language">{language}</span>
        <button type="button" className="code-copy" onClick={() => void copy()}>
          {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {copied ? t('concept.copied') : t('concept.copy')}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  )
}

// La ficha terminada. Todo lo que escribió la IA se pinta como texto, nunca como HTML
// (diseno-tecnico.md §5.3); los saltos de línea se respetan con CSS.
export default function CardView({ concept }: { concept: ConceptDetail }) {
  const { t } = useTranslation()
  const card = concept.card
  if (!card) return null
  const typedDiffers = concept.title.trim().toLowerCase() !== card.canonical_title.trim().toLowerCase()

  return (
    <article className="ficha">
      <header className="ficha-header">
        <h1>{card.canonical_title}</h1>
        {typedDiffers ? <p className="muted">{t('concept.youWrote', { title: concept.title })}</p> : null}
      </header>
      <section className="ficha-section">
        <h2>{t('concept.sections.what_is')}</h2>
        <p className="reading">{card.what_is}</p>
      </section>
      <section className="ficha-section">
        <h2>{t('concept.sections.what_for')}</h2>
        <p className="reading">{card.what_for}</p>
      </section>
      <section className="ficha-section">
        <h2>{t('concept.sections.example')}</h2>
        <p className="reading">{card.example}</p>
        {card.example_code ? <CodeBlock code={card.example_code} language={card.example_code_language} /> : null}
      </section>
    </article>
  )
}
