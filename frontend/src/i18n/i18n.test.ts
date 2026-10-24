import { describe, expect, it } from 'vitest'

import en from './en.json'
import es from './es.json'

// Recorre el árbol y devuelve «ruta → texto» de cada hoja.
function leaves(tree: unknown, prefix = ''): Record<string, string> {
  if (typeof tree === 'string') return { [prefix]: tree }
  return Object.entries(tree as Record<string, unknown>).reduce(
    (all, [key, value]) => ({ ...all, ...leaves(value, prefix ? `${prefix}.${key}` : key) }),
    {},
  )
}

const placeholders = (text: string) => [...text.matchAll(/\{\{(\w+)\}\}/g)].map((match) => match[1]).sort()

describe('idiomas', () => {
  const spanish = leaves(es)
  const english = leaves(en)

  it('es y en tienen exactamente las mismas claves', () => {
    expect(Object.keys(english).sort()).toEqual(Object.keys(spanish).sort())
  })

  it('cada texto lleva los mismos {{parámetros}} en los dos idiomas', () => {
    for (const [key, text] of Object.entries(spanish)) {
      expect(placeholders(english[key] ?? ''), key).toEqual(placeholders(text))
    }
  })

  it('ningún texto está vacío', () => {
    for (const [key, text] of [...Object.entries(spanish), ...Object.entries(english)]) {
      expect(text.trim(), key).not.toBe('')
    }
  })
})
