import { useEffect, useState } from 'react'

function App() {
  const [health, setHealth] = useState<string>('consultando…')

  useEffect(() => {
    fetch('/api/v1/health')
      .then((res) => res.json())
      .then((data) => setHealth(JSON.stringify(data)))
      .catch(() => setHealth('error al conectar con la API'))
  }, [])

  return (
    <main>
      <h1>CompaBook</h1>
      <p>API: {health}</p>
    </main>
  )
}

export default App
