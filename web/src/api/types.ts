export interface TrainLight {
  id: string
  numero: string
  servicio: string
  linea: string | null
  color: string
  lat: number
  lon: number
  rumbo: number | null
  retraso_min: number | null
  estado: string
}

export interface FeedInfo {
  edad_s: number
  stale: boolean
}

export type Feeds = Record<string, FeedInfo>

export interface TrainsResponse {
  trenes: TrainLight[]
  feeds: Feeds
  generado: number
}

export type StopState = 'pasada' | 'proxima' | 'pendiente' | 'suprimida'

export interface Parada {
  id: string
  nombre: string
  lat: number | null
  lon: number | null
  ts_prog: number
  ts_est: number
  hora_prog: string
  hora_est: string
  retraso_s: number
  estado: StopState
}

export interface NextStop {
  id: string
  nombre: string
  hora_prog: string
  hora_est: string
}

export type LngLat = [number, number]

export interface TrainDetail extends TrainLight {
  source: 'LD' | 'CER'
  trip_id: string
  fecha: string
  origen: string | null
  destino: string | null
  proxima_parada: NextStop | null
  anden: string | null
  progreso: number | null
  casado_con_horario: boolean
  cancelado: boolean
  ts: number
  paradas: Parada[]
  shape: LngLat[]
}

export interface Station {
  id: string
  nombre: string
  lat: number
  lon: number
  dist_m?: number
}

export interface SearchResponse {
  trenes: TrainLight[]
  estaciones: Station[]
}

export type BoardKind = 'salidas' | 'llegadas'

export interface BoardRow {
  ts_prog: number
  hora_prog: string
  hora_est: string
  retraso_min: number | null
  origen: string
  destino: string
  servicio: string
  linea: string | null
  numero: string
  anden: string | null
  estado: 'programado' | 'en_circulacion' | 'cancelado' | 'suprimida'
  train_id: string | null
}

export interface BoardResponse {
  estacion: Station
  tipo: BoardKind
  filas: BoardRow[]
}

export interface Avisos {
  retraso: boolean
  cancelacion: boolean
  anden: boolean
  salida: boolean
}

export type FavoriteKind = 'tren' | 'estacion'

export interface Favorite {
  tipo: FavoriteKind
  ref: string
  avisos: Avisos
}
