import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [health, setHealth] = useState('checking...')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setHealth(data.status ?? 'unknown'))
      .catch(() => setHealth('unreachable'))
  }, [])

  return (
    <div className="app">
      <h1>Policy Time Machine</h1>
      <p>Deploy-envelope smoke test</p>
      <p>
        API health: <strong>{health}</strong>
      </p>
    </div>
  )
}

export default App
