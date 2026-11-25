import { useEffect, useState } from 'react'
import type { Avisos, Favorite, FavoriteKind, TrainLight } from '../api/types'
import { delayLabel, delayLevel, trainTitle } from '../lib/format'
import type { PushResult } from '../lib/push'
import { disablePush, enablePush, pushEnabled, pushSupported } from '../lib/push'

interface Props {
  favorites: Favorite[]
  trains: TrainLight[]
  onAvisos(fav: Favorite, avisos: Avisos): void
  onRemove(tipo: FavoriteKind, ref: string): void
  onTrain(id: string): void
  onStation(id: string): void
  onClose(): void
}

const AVISO_LABEL: Record<keyof Avisos, string> = {
  retraso: 'Retraso',
  cancelacion: 'Cancelación',
  anden: 'Cambio de andén',
  salida: 'Sale en 15 min',
}

const PUSH_MESSAGE: Record<PushResult, string> = {
  ok: 'Avisos activados en este dispositivo.',
  denied: 'El navegador ha bloqueado las notificaciones para esta página.',
  unsupported: 'Este navegador no admite avisos, o la página no está en HTTPS.',
  unconfigured: 'El servidor no tiene configurados los avisos push.',
  error: 'No se pudieron activar los avisos.',
}

export function FavoritesPanel({ favorites, trains, onAvisos, onRemove, onTrain, onStation, onClose }: Props) {
  const [enabled, setEnabled] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    // getRegistration puede rechazar (p. ej. almacenamiento bloqueado): se deja como desactivado.
    pushEnabled().then(setEnabled).catch(() => undefined)
  }, [])

  const togglePush = async () => {
    if (enabled) {
      await disablePush()
      setEnabled(false)
      setMessage('Avisos desactivados en este dispositivo.')
      return
    }
    const result = await enablePush()
    setEnabled(result === 'ok')
    setMessage(PUSH_MESSAGE[result])
  }

  const trenes = favorites.filter((f) => f.tipo === 'tren')
  const estaciones = favorites.filter((f) => f.tipo === 'estacion')

  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <strong className="grow">Favoritos</strong>
      </div>
      <div className="panel-body">
        <div className="row">
          <span>Avisos en este dispositivo</span>
          <button onClick={() => void togglePush()} disabled={!pushSupported()} aria-pressed={enabled}>
            {enabled ? 'Desactivar' : 'Activar'}
          </button>
        </div>
        {!pushSupported() && <p className="muted small">Los avisos necesitan HTTPS (o localhost) y un navegador compatible.</p>}
        {message && <p className="muted small">{message}</p>}

        <h3>Trenes</h3>
        {trenes.length === 0 && <p className="muted">Abre un tren y pulsa «Favorito» para seguirlo.</p>}
        {trenes.map((fav) => {
          const live = trains.find((t) => t.numero === fav.ref)
          return (
            <div key={fav.ref} className="fav">
              <div className="row">
                <button className="link grow" disabled={!live} onClick={() => live && onTrain(live.id)}>
                  {live ? trainTitle(live) : `Tren ${fav.ref}`}
                </button>
                {live
                  ? <span className={`chip delay-${delayLevel(live.retraso_min)}`}>{delayLabel(live.retraso_min)}</span>
                  : <span className="muted small">No circula ahora</span>}
                <button className="icon-btn" onClick={() => onRemove('tren', fav.ref)} aria-label="Quitar favorito">✕</button>
              </div>
              <div className="avisos">
                {(Object.keys(AVISO_LABEL) as (keyof Avisos)[]).map((key) => (
                  <label key={key}>
                    <input type="checkbox" checked={fav.avisos[key]}
                           onChange={(e) => onAvisos(fav, { ...fav.avisos, [key]: e.target.checked })} />
                    {AVISO_LABEL[key]}
                  </label>
                ))}
              </div>
            </div>
          )
        })}

        <h3>Estaciones</h3>
        {estaciones.length === 0 && <p className="muted">Abre una estación y pulsa la estrella para guardarla.</p>}
        {estaciones.map((fav) => (
          <div key={fav.ref} className="row">
            <button className="link grow" onClick={() => onStation(fav.ref)}>Estación {fav.ref}</button>
            <button className="icon-btn" onClick={() => onRemove('estacion', fav.ref)} aria-label="Quitar favorita">✕</button>
          </div>
        ))}
      </div>
    </section>
  )
}
