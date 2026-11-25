import type { LngLat } from '../api/types'

const MAX_ANIMATED_JUMP_DEG = 0.5

interface Positioned {
  id: string
  lon: number
  lat: number
}

/** Posiciones a mostrar en el instante t (0..1) de la animación entre dos lecturas. */
export function interpolate(prev: Map<string, LngLat>, next: Positioned[], t: number): Map<string, LngLat> {
  const out = new Map<string, LngLat>()
  for (const train of next) {
    const from = prev.get(train.id)
    const jump = from ? Math.max(Math.abs(train.lon - from[0]), Math.abs(train.lat - from[1])) : 0
    if (!from || t >= 1 || jump > MAX_ANIMATED_JUMP_DEG) {
      out.set(train.id, [train.lon, train.lat])
    } else {
      out.set(train.id, [from[0] + (train.lon - from[0]) * t, from[1] + (train.lat - from[1]) * t])
    }
  }
  return out
}

/** Distancia al cuadrado de p al segmento a-b, en grados corregidos por la latitud. */
function segmentDistance2(p: LngLat, a: LngLat, b: LngLat): number {
  const k = Math.cos((p[1] * Math.PI) / 180)
  const ax = (a[0] - p[0]) * k
  const ay = a[1] - p[1]
  const dx = (b[0] - a[0]) * k
  const dy = b[1] - a[1]
  const len2 = dx * dx + dy * dy
  const t = len2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0
  const x = ax + t * dx
  const y = ay + t * dy
  return x * x + y * y
}

/** Parte el trazado en lo ya recorrido y lo pendiente, cortando en el tramo más cercano a p. */
export function splitRoute(shape: LngLat[], p: LngLat): { done: LngLat[]; pending: LngLat[] } {
  if (shape.length < 2) return { done: [], pending: shape }
  let best = 0
  let bestDist = Infinity
  for (let i = 0; i < shape.length - 1; i++) {
    const d = segmentDistance2(p, shape[i], shape[i + 1])
    if (d < bestDist) {
      bestDist = d
      best = i
    }
  }
  return { done: [...shape.slice(0, best + 1), p], pending: [p, ...shape.slice(best + 1)] }
}

/** [[oeste, sur], [este, norte]] o null si no hay puntos. */
export function bounds(points: LngLat[]): [LngLat, LngLat] | null {
  if (!points.length) return null
  const lons = points.map((p) => p[0])
  const lats = points.map((p) => p[1])
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ]
}

const EARTH_M = 6_371_000
const rad = (d: number) => (d * Math.PI) / 180

/** Distancia en metros entre dos puntos [lon, lat]. */
export function distanceM(a: LngLat, b: LngLat): number {
  const dLat = rad(b[1] - a[1])
  const dLon = rad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_M * Math.asin(Math.sqrt(h))
}

/** Los elementos más cercanos a p, como mucho a maxM metros, ordenados por distancia. */
export function nearest<T extends Positioned>(items: T[], p: LngLat, maxM: number, limit: number): (T & { dist_m: number })[] {
  return items
    .map((it) => ({ ...it, dist_m: distanceM(p, [it.lon, it.lat]) }))
    .filter((it) => it.dist_m <= maxM)
    .sort((a, b) => a.dist_m - b.dist_m)
    .slice(0, limit)
}

/** Polígono (anillo cerrado) que aproxima un círculo de radio m metros alrededor de c. */
export function circle(c: LngLat, m: number, steps = 48): LngLat[] {
  const dLat = (m / EARTH_M) * (180 / Math.PI)
  const dLon = dLat / Math.cos(rad(c[1]))
  const ring: LngLat[] = []
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI
    ring.push([c[0] + dLon * Math.cos(a), c[1] + dLat * Math.sin(a)])
  }
  return ring
}

export function distanceLabel(m: number): string {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0).replace('.', ',')} km`
}
