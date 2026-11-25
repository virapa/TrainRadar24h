import { useEffect, useMemo, useState } from 'react'
import { stationsNear } from '../api/client'
import type { Station, TrainLight } from '../api/types'
import type { Location } from '../hooks/useLocation'
import { delayLabel, delayLevel, trainTitle } from '../lib/format'
import { distanceLabel, nearest } from '../lib/geo'

const TRAIN_RADIUS_M = 25_000
const MAX_TRAINS = 15
const STATIONS_REFRESH_M = 500

interface Props {
  location: Location
  trains: TrainLight[]
  onRetry(): void
  onTrain(id: string): void
  onStation(id: string): void
  onClose(): void
}

const STATUS_MESSAGE: Partial<Record<Location['status'], string>> = {
  idle: 'Pidiendo permiso de ubicación…',
  waiting: 'Buscando tu ubicación…',
  denied: 'El permiso de ubicación está bloqueado. Actívalo en los ajustes del sitio de tu navegador y pulsa «Reintentar».',
  unsupported: 'Este navegador no permite obtener la ubicación en esta página. En el móvil la app tiene que abrirse por HTTPS.',
  error: 'No se pudo obtener la ubicación.',
}

export function NearbyPanel({ location, trains, onRetry, onTrain, onStation, onClose }: Props) {
  const { pos, status } = location
  const [stations, setStations] = useState<Station[] | null>(null)
  const [stationsAt, setStationsAt] = useState<[number, number] | null>(null)
  const [stationsError, setStationsError] = useState(false)

  const nearTrains = useMemo(() => (pos ? nearest(trains, pos, TRAIN_RADIUS_M, MAX_TRAINS) : []), [trains, pos])

  // Estaciones: se piden al tener posición y otra vez si te mueves más de 500 m.
  useEffect(() => {
    if (!pos) return
    if (stationsAt && Math.hypot((pos[0] - stationsAt[0]) * 85_000, (pos[1] - stationsAt[1]) * 111_000) < STATIONS_REFRESH_M) return
    setStationsAt(pos)
    stationsNear(pos[1], pos[0])
      .then((list) => { setStations(list); setStationsError(false) })
      .catch(() => setStationsError(true))
  }, [pos, stationsAt])

  const message = pos ? null : STATUS_MESSAGE[status]
  const canRetry = !pos && (status === 'denied' || status === 'error')

  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <strong className="grow">Cerca de ti</strong>
      </div>
      <div className="panel-body">
        {message && <p className="muted">{message}</p>}
        {canRetry && <button className="row" onClick={onRetry}>Reintentar</button>}

        {pos && (
          <>
            <h3>Trenes a menos de {TRAIN_RADIUS_M / 1000} km</h3>
            {nearTrains.length === 0 && <p className="muted">No hay trenes circulando cerca (con los filtros actuales).</p>}
            {nearTrains.map((t) => (
              <button key={t.id} className="row" onClick={() => onTrain(t.id)}>
                <span className="grow">{trainTitle(t)}</span>
                <span className="muted small">{distanceLabel(t.dist_m)}</span>
                <span className={`chip delay-${delayLevel(t.retraso_min)}`}>{delayLabel(t.retraso_min)}</span>
              </button>
            ))}

            <h3>Estaciones cercanas</h3>
            {stationsError && <p className="muted">No se pudieron cargar las estaciones cercanas.</p>}
            {!stations && !stationsError && <p className="muted">Cargando…</p>}
            {stations?.map((s) => (
              <button key={s.id} className="row" onClick={() => onStation(s.id)}>
                <span className="grow">{s.nombre}</span>
                {s.dist_m !== undefined && <span className="muted small">{distanceLabel(s.dist_m)}</span>}
              </button>
            ))}
          </>
        )}
      </div>
    </section>
  )
}
