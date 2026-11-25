import { beforeEach, describe, expect, it } from 'vitest'
import type { TrainLight } from '../api/types'
import { applyFilters, DEFAULT_FILTERS, loadFilters, saveFilters } from './filters'
import { loadPrefs, savePrefs } from './prefs'

function train(servicio: string, retraso_min: number | null): TrainLight {
  return { id: servicio + retraso_min, numero: '1', servicio, linea: null, color: '#000000', lat: 0, lon: 0,
           rumbo: null, retraso_min, estado: 'IN_TRANSIT_TO' }
}

const TRAINS = [train('AVE', 0), train('MD', 12), train('CERCANIAS', 3), train('CERCANIAS', null)]

describe('applyFilters', () => {
  it('por defecto muestra todo', () => {
    expect(applyFilters(TRAINS, DEFAULT_FILTERS)).toHaveLength(4)
  })
  it('oculta categorías', () => {
    const out = applyFilters(TRAINS, { ...DEFAULT_FILTERS, cer: false })
    expect(out.map((t) => t.servicio)).toEqual(['AVE', 'MD'])
  })
  it('solo con retraso de 5 min o más', () => {
    const out = applyFilters(TRAINS, { ...DEFAULT_FILTERS, soloRetraso: true })
    expect(out.map((t) => t.servicio)).toEqual(['MD'])
  })
})

describe('persistencia', () => {
  beforeEach(() => localStorage.clear())
  it('filtros: valores por defecto, guardado y datos corruptos', () => {
    expect(loadFilters()).toEqual(DEFAULT_FILTERS)
    saveFilters({ ...DEFAULT_FILTERS, md: false })
    expect(loadFilters().md).toBe(false)
    localStorage.setItem('tr24.filters', '{no es json')
    expect(loadFilters()).toEqual(DEFAULT_FILTERS)
  })
  it('preferencias: tema oscuro por defecto', () => {
    expect(loadPrefs()).toEqual({ theme: 'dark', rails: false })
    savePrefs({ theme: 'light', rails: true })
    expect(loadPrefs()).toEqual({ theme: 'light', rails: true })
  })
})
