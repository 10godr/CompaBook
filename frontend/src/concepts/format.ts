// Fecha corta («24 oct 2026») en el idioma de la web y la zona horaria de la cuenta.
export function formatDate(iso: string, language: string, timeZone?: string): string {
  try {
    return new Intl.DateTimeFormat(language, { day: 'numeric', month: 'short', year: 'numeric', timeZone }).format(
      new Date(iso),
    )
  } catch {
    return ''
  }
}
