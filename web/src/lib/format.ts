import type { Feeds } from '../api/types'

export type Category = 'ave' | 'ld' | 'md' | 'cer'

const ALTA_VELOCIDAD = new Set(['AVE', 'AVLO', 'AVE INT', 'EUROMED'])
const MEDIA_DISTANCIA = new Set(['MD', 'REGIONAL', 'REG.EXP.', 'AVANT', 'PROXIMDAD'])

export const CATEGORY_COLOR: Record<Category, string> = {
  ave: '#E0457B',
  ld: '#B57BEE',
  md: '#F5A623',
  cer: '#4FC3F7',
}

export const CATEGORY_NAME: Record<Category, string> = {
  ave: 'Alta velocidad',
  ld: 'Larga distancia',
  md: 'Media distancia y regionales',
  cer: 'Cercanías',
}

const DEFAULT_API_COLOR = '#9AA0A6'

export function category(servicio: string): Category {
  if (servicio === 'CERCANIAS') return 'cer'
  const s = servicio.toUpperCase()
  if (ALTA_VELOCIDAD.has(s)) return 'ave'
  return MEDIA_DISTANCIA.has(s) ? 'md' : 'ld'
}

/** Color del icono: el de la línea en Cercanías, uno por categoría en el resto. */
export function trainColor(t: { servicio: string; color: string }): string {
  const cat = category(t.servicio)
  const usable = /^#[0-9a-f]{6}$/i.test(t.color) && t.color.toUpperCase() !== DEFAULT_API_COLOR
  return cat === 'cer' && usable ? t.color : CATEGORY_COLOR[cat]
}

export type DelayLevel = 'none' | 'ok' | 'warn' | 'bad'

export function delayLevel(min: number | null): DelayLevel {
  if (min === null) return 'none'
  if (min < 5) return 'ok'
  return min < 15 ? 'warn' : 'bad'
}

export function delayLabel(min: number | null): string {
  if (min === null) return 'Sin datos'
  return min < 1 ? 'En hora' : `+${min} min`
}

export function trainTitle(t: { servicio: string; numero: string; linea: string | null }): string {
  if (t.servicio === 'CERCANIAS') return `Cercanías ${t.linea ? `${t.linea} ` : ''}· ${t.numero}`
  return `${t.servicio} ${t.numero}`
}

export function agoLabel(seconds: number): string {
  if (seconds < 60) return `hace ${seconds} s`
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`
  return `hace ${Math.floor(seconds / 3600)} h`
}

const FEED_NAME: Record<string, string> = { LD: 'Larga y Media Distancia', CER: 'Cercanías' }
const STALE_AFTER_S = 180

export interface Freshness {
  label: string
  level: 'ok' | 'warn'
}

/** Texto de frescura de los datos. checkedAt: ms de la última lectura correcta, o null si no hay. */
export function freshness(feeds: Feeds, checkedAt: number | null, nowMs: number, online: boolean): Freshness {
  if (checkedAt === null) {
    return online ? { label: 'Cargando…', level: 'ok' } : { label: 'Sin conexión', level: 'warn' }
  }
  const ago = agoLabel(Math.max(0, Math.round((nowMs - checkedAt) / 1000)))
  if (!online) return { label: `Sin conexión · datos de ${ago}`, level: 'warn' }
  const late = Object.entries(feeds).find(([, f]) => f.stale || f.edad_s > STALE_AFTER_S)
  if (late) {
    const [key, feed] = late
    return { label: `${FEED_NAME[key] ?? key}: datos de ${agoLabel(feed.edad_s)}`, level: 'warn' }
  }
  return { label: ago, level: 'ok' }
}
