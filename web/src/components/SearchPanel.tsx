import { useEffect, useState } from 'react'
import { search, stationsNear } from '../api/client'
import type { SearchResponse, Station } from '../api/types'
import { delayLabel, delayLevel, trainTitle } from '../lib/format'

interface Props {
  onClose(): void
  onTrain(id: string): void
  onStation(id: string): void
}

const DEBOUNCE_MS = 300
const EMPTY: SearchResponse = { trenes: [], estaciones: [] }

export function SearchPanel({ onClose, onTrain, onStation }: Props) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SearchResponse>(EMPTY)
  const [near, setNear] = useState<Station[] | null>(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    const text = q.trim()
    if (text.length < 2) {
      setResults(EMPTY)
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      search(text)
        .then((r) => { if (!cancelled) { setResults(r); setMessage('') } })
        .catch(() => { if (!cancelled) setMessage('No se pudo buscar. Comprueba la conexión.') })
    }, DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [q])

  const findNear = () => {
    if (!navigator.geolocation) {
      setMessage('Este navegador no permite obtener la ubicación.')
      return
    }
    setMessage('Buscando tu ubicación…')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        stationsNear(pos.coords.latitude, pos.coords.longitude)
          .then((list) => { setNear(list); setMessage('') })
          .catch(() => setMessage('No se pudieron cargar las estaciones cercanas.'))
      },
      () => setMessage('No se pudo obtener la ubicación.'),
    )
  }

  const typed = q.trim().length >= 2
  const nothing = typed && !message && results.trenes.length === 0 && results.estaciones.length === 0

  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} inputMode="search"
               placeholder="Ej.: 03304, Atocha, Sants" aria-label="Buscar tren o estación" />
      </div>
      <div className="panel-body">
        {message && <p className="muted">{message}</p>}
        {!typed && (
          <button className="row" onClick={findNear}>Estaciones cerca de mí</button>
        )}
        {!typed && near?.map((s) => (
          <button key={s.id} className="row" onClick={() => onStation(s.id)}>
            <span>{s.nombre}</span>
            <span className="muted">{s.dist_m !== undefined && (s.dist_m < 1000 ? `${s.dist_m} m` : `${(s.dist_m / 1000).toFixed(1)} km`)}</span>
          </button>
        ))}
        {results.trenes.length > 0 && <h3>Trenes</h3>}
        {results.trenes.map((t) => (
          <button key={t.id} className="row" onClick={() => onTrain(t.id)}>
            <span>{trainTitle(t)}</span>
            <span className={`chip delay-${delayLevel(t.retraso_min)}`}>{delayLabel(t.retraso_min)}</span>
          </button>
        ))}
        {results.estaciones.length > 0 && <h3>Estaciones</h3>}
        {results.estaciones.map((s) => (
          <button key={s.id} className="row" onClick={() => onStation(s.id)}>{s.nombre}</button>
        ))}
        {nothing && <p className="muted">Sin resultados. Los trenes se buscan por número y solo aparecen si están circulando.</p>}
      </div>
    </section>
  )
}
