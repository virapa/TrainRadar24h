import type { Avisos, BoardKind, BoardResponse, Favorite, FavoriteKind, SearchResponse, Station, TrainDetail,
              TrainsResponse } from './types'

const DEVICE_KEY = 'tr24.device'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function randomId(): string {
  // crypto.randomUUID solo existe en contexto seguro (HTTPS o localhost).
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return Array.from({ length: 4 }, () => Math.random().toString(36).slice(2, 10)).join('')
}

/** Identificador anónimo de este navegador; con él se guardan favoritos y avisos. */
export function deviceId(): string {
  let id = localStorage.getItem(DEVICE_KEY)
  if (!id) {
    id = randomId()
    localStorage.setItem(DEVICE_KEY, id)
  }
  return id
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) throw new ApiError(res.status, `${res.status} en ${path}`)
  return (await res.json()) as T
}

function asDevice(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'X-Device-Id': deviceId(), 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }
}

export interface TrainsResult {
  data: TrainsResponse | null // null: el servidor respondió 304, nada ha cambiado
  etag: string | null
}

export async function getTrains(etag: string | null): Promise<TrainsResult> {
  const res = await fetch('/api/trains', { headers: etag ? { 'If-None-Match': etag } : {} })
  if (res.status === 304) return { data: null, etag }
  if (!res.ok) throw new ApiError(res.status, `${res.status} en /trains`)
  return { data: (await res.json()) as TrainsResponse, etag: res.headers.get('ETag') }
}

export const getTrain = (id: string) => request<TrainDetail>(`/trains/${encodeURIComponent(id)}`)

export const search = (q: string) => request<SearchResponse>(`/search?q=${encodeURIComponent(q)}`)

export const stationsNear = (lat: number, lon: number) => request<Station[]>(`/stations/near?lat=${lat}&lon=${lon}`)

export const getBoard = (stationId: string, tipo: BoardKind) =>
  request<BoardResponse>(`/stations/${encodeURIComponent(stationId)}/board?tipo=${tipo}`)

export const listFavorites = () => request<Favorite[]>('/favorites', asDevice('GET'))

export const putFavorite = (fav: { tipo: FavoriteKind; ref: string; avisos?: Avisos }) =>
  request<{ ok: boolean }>('/favorites', asDevice('PUT', fav))

export const deleteFavorite = (tipo: FavoriteKind, ref: string) =>
  request<{ ok: boolean }>(`/favorites?tipo=${tipo}&ref=${encodeURIComponent(ref)}`, asDevice('DELETE'))

export const getVapidKey = () => request<{ key: string }>('/push/vapid-public-key')

export const saveSubscription = (sub: { endpoint: string; keys: Record<string, string> }) =>
  request<{ ok: boolean }>('/push/subscription', asDevice('POST', sub))

export const deleteSubscription = () => request<{ ok: boolean }>('/push/subscription', asDevice('DELETE'))
