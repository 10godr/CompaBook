import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import App from '../App'

// Monta la aplicación entera en la ruta indicada (el router usa la URL real de jsdom).
export function renderApp(path: string) {
  window.history.pushState({}, '', path)
  return { user: userEvent.setup(), ...render(<App />) }
}
