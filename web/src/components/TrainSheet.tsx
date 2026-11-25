import { useState } from 'react'
import type { TrainDetail } from '../api/types'
import { delayLabel, delayLevel, trainTitle } from '../lib/format'
import { buildPath } from '../lib/route'

interface Props {
  detail: TrainDetail | null
  gone: boolean
  favorite: boolean
  following: boolean
  onClose(): void
  onFavorite(numero: string): void
  onFollow(): void
  onRoute(): void
  onStation(id: string): void
}

async function share(d: TrainDetail): Promise<void> {
  const trayecto = d.origen && d.destino ? ` ${d.origen} → ${d.destino}` : ''
  const text = `${trainTitle(d)}${trayecto} · ${delayLabel(d.retraso_min)}`
  const url = location.origin + buildPath({ kind: 'train', id: d.id })
  try {
    if (navigator.share) await navigator.share({ title: trainTitle(d), text, url })
    else await navigator.clipboard.writeText(`${text} ${url}`)
  } catch {
    // El usuario canceló o el navegador no lo permite: no hay nada que hacer.
  }
}

export function TrainSheet({ detail, gone, favorite, following, onClose, onFavorite, onFollow, onRoute, onStation }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (gone) {
    return (
      <section className="sheet">
        <div className="sheet-head">
          <strong>Este tren ya no está en circulación</strong>
          <button className="icon-btn" onClick={onClose} aria-label="Cerrar">✕</button>
        </div>
      </section>
    )
  }
  if (!detail) {
    return (
      <section className="sheet">
        <p className="muted">Cargando…</p>
      </section>
    )
  }

  const suprimidas = detail.paradas.filter((p) => p.estado === 'suprimida')
  const next = detail.proxima_parada

  return (
    <section className={`sheet ${expanded ? 'expanded' : ''}`}>
      <div className="sheet-head">
        <div>
          <strong className="train-title">{trainTitle(detail)}</strong>
          <span className={`chip delay-${delayLevel(detail.retraso_min)}`}>{delayLabel(detail.retraso_min)}</span>
          {detail.anden && <span className="chip">Andén {detail.anden}</span>}
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Cerrar">✕</button>
      </div>

      {detail.origen && detail.destino ? (
        <>
          <div className="trip">
            <span>{detail.origen}</span>
            <span className="arrow">→</span>
            <span>{detail.destino}</span>
          </div>
          <div className="progress" role="progressbar" aria-valuenow={Math.round((detail.progreso ?? 0) * 100)}
               aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${Math.round((detail.progreso ?? 0) * 100)}%` }} />
          </div>
        </>
      ) : (
        <p className="muted">Renfe no publica el recorrido de este tren.</p>
      )}

      {next && (
        <p className="next">
          Próxima parada:{' '}
          <button className="link" onClick={() => onStation(next.id)}>{next.nombre}</button>{' '}
          a las <strong>{next.hora_est}</strong>
          {next.hora_est !== next.hora_prog && <span className="muted"> (prevista {next.hora_prog})</span>}
        </p>
      )}

      {detail.cancelado && <p className="notice bad">Renfe marca este tren como cancelado.</p>}
      {!detail.cancelado && suprimidas.length > 0 && (
        <p className="notice warn">Según Renfe, no para en: {suprimidas.map((p) => p.nombre).join(', ')}.</p>
      )}

      <div className="actions">
        <button onClick={() => onFavorite(detail.numero)} aria-pressed={favorite}>{favorite ? '★ Favorito' : '☆ Favorito'}</button>
        <button onClick={onFollow} aria-pressed={following}>{following ? 'Siguiendo' : 'Seguir'}</button>
        <button onClick={onRoute} disabled={detail.shape.length < 2}>Ruta</button>
        <button onClick={() => void share(detail)}>Compartir</button>
        <button onClick={() => setExpanded(!expanded)} disabled={detail.paradas.length === 0}>
          {expanded ? 'Menos' : 'Paradas'}
        </button>
      </div>

      {expanded && (
        <ol className="stops">
          {detail.paradas.map((p) => (
            <li key={p.id + p.ts_prog} className={`stop ${p.estado}`}>
              <span className="time">
                {p.hora_est !== p.hora_prog && <s>{p.hora_prog}</s>} {p.hora_est}
              </span>
              <button className="link" onClick={() => onStation(p.id)}>{p.nombre}</button>
              {p.estado === 'suprimida' && <span className="chip delay-bad">Suprimida</span>}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
