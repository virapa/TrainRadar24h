import type { TrainLight } from '../api/types'
import { category } from './format'

export interface Filters {
  ave: boolean
  ld: boolean
  md: boolean
  cer: boolean
  soloRetraso: boolean
}

export const DEFAULT_FILTERS: Filters = { ave: true, ld: true, md: true, cer: true, soloRetraso: false }
const KEY = 'tr24.filters'
const MIN_DELAY = 5

export function applyFilters(trains: TrainLight[], f: Filters): TrainLight[] {
  return trains.filter((t) => f[category(t.servicio)] && (!f.soloRetraso || (t.retraso_min ?? 0) >= MIN_DELAY))
}

export function loadFilters(): Filters {
  try {
    return { ...DEFAULT_FILTERS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch {
    return DEFAULT_FILTERS
  }
}

export function saveFilters(f: Filters): void {
  localStorage.setItem(KEY, JSON.stringify(f))
}
