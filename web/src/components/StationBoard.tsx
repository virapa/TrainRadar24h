import { useEffect, useState } from 'react'
import { ApiError, getBoard } from '../api/client'
import type { BoardKind, BoardResponse, BoardRow } from '../api/types'
import { delayLevel } from '../lib/format'

interface Props {
  stationId: string
  favorite: boolean
  onClose(): void
  onFavorite(): void
  onTrain(id: string): void
}

const POLL_MS = 30_000

function statusText(row: BoardRow): string {
  if (row.estado === 'cancelado') return 'Cancelado'
  if (row.estado === 'suprimida') return 'No para'
  if (row.retraso_min === null) return ''
  return row.retraso_min < 1 ? 'En hora' : `+${row.retraso_min} min`
}

export function StationBoard({ stationId, favorite, onClose, onFavorite, onTrain }: Props) {
  const [tipo, setTipo] = useState<BoardKind>('salidas')
  const [board, setBoard] = useState<BoardResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    setBoard(null)
    setError('')
    const tick = async () => {
      try {
        const next = await getBoard(stationId, tipo)
        if (stopped) return
        setBoard(next)
        setError('')
      } catch (err) {
        if (stopped) return
        setError(err instanceof ApiError && err.status === 404 ? 'Estación no encontrada.' : 'No se pudo cargar el panel.')
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS)
    }
    void tick()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [stationId, tipo])

  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <strong className="grow">{board?.estacion.nombre ?? 'Estación'}</strong>
        <button className="icon-btn" onClick={onFavorite} aria-pressed={favorite} aria-label="Favorita">{favorite ? '★' : '☆'}</button>
      </div>
      <div className="tabs" role="tablist">
        {(['salidas', 'llegadas'] as const).map((k) => (
          <button key={k} role="tab" aria-selected={tipo === k} onClick={() => setTipo(k)}>
            {k === 'salidas' ? 'Salidas' : 'Llegadas'}
          </button>
        ))}
      </div>
      <div className="panel-body">
        {error && <p className="muted">{error}</p>}
        {!error && !board && <p className="muted">Cargando…</p>}
        {board && board.filas.length === 0 && <p className="muted">No hay trenes en las próximas 3 horas.</p>}
        {board?.filas.map((row) => (
          <button key={`${row.numero}-${row.ts_prog}`} className="row board-row" disabled={!row.train_id}
                  onClick={() => row.train_id && onTrain(row.train_id)}>
            <span className="time">
              {row.hora_est !== row.hora_prog && <s>{row.hora_prog}</s>} {row.hora_est}
            </span>
            <span className="grow">
              <span>{tipo === 'salidas' ? row.destino : row.origen}</span>
              <small className="muted">
                {row.linea ?? row.servicio} {row.numero}{row.anden ? ` · Andén ${row.anden}` : ''}
              </small>
            </span>
            <span className={`chip delay-${row.estado === 'cancelado' || row.estado === 'suprimida' ? 'bad' : delayLevel(row.retraso_min)}`}>
              {statusText(row) || 'Programado'}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}
