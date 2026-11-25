import { describe, expect, it } from 'vitest'
import { agoLabel, category, delayLabel, delayLevel, freshness, trainColor, trainTitle } from './format'

describe('category', () => {
  it('clasifica los servicios reales de Renfe', () => {
    expect(category('AVE')).toBe('ave')
    expect(category('AVLO')).toBe('ave')
    expect(category('AVE INT')).toBe('ave')
    expect(category('EUROMED')).toBe('ave')
    expect(category('ALVIA')).toBe('ld')
    expect(category('Intercity')).toBe('ld')
    expect(category('LD')).toBe('ld')
    expect(category('MD')).toBe('md')
    expect(category('REG.EXP.')).toBe('md')
    expect(category('AVANT')).toBe('md')
    expect(category('CERCANIAS')).toBe('cer')
  })
})

describe('trainColor', () => {
  it('usa color por categoría en larga y media distancia', () => {
    expect(trainColor({ servicio: 'AVE', color: '#F2F5F5' })).toBe('#E0457B')
    expect(trainColor({ servicio: 'MD', color: '#F2F5F5' })).toBe('#F5A623')
  })
  it('usa el color de la línea en Cercanías, salvo el gris por defecto', () => {
    expect(trainColor({ servicio: 'CERCANIAS', color: '#75B6E0' })).toBe('#75B6E0')
    expect(trainColor({ servicio: 'CERCANIAS', color: '#9AA0A6' })).toBe('#4FC3F7')
    expect(trainColor({ servicio: 'CERCANIAS', color: 'rojo' })).toBe('#4FC3F7')
  })
})

describe('retraso', () => {
  it('nivel', () => {
    expect(delayLevel(null)).toBe('none')
    expect(delayLevel(-3)).toBe('ok')
    expect(delayLevel(4)).toBe('ok')
    expect(delayLevel(5)).toBe('warn')
    expect(delayLevel(14)).toBe('warn')
    expect(delayLevel(15)).toBe('bad')
  })
  it('texto', () => {
    expect(delayLabel(null)).toBe('Sin datos')
    expect(delayLabel(0)).toBe('En hora')
    expect(delayLabel(-3)).toBe('En hora')
    expect(delayLabel(7)).toBe('+7 min')
  })
})

describe('trainTitle', () => {
  it('compone el título', () => {
    expect(trainTitle({ servicio: 'AVE', numero: '03304', linea: null })).toBe('AVE 03304')
    expect(trainTitle({ servicio: 'CERCANIAS', numero: '35903', linea: 'C5' })).toBe('Cercanías C5 · 35903')
    expect(trainTitle({ servicio: 'CERCANIAS', numero: '35903', linea: null })).toBe('Cercanías · 35903')
  })
})

describe('agoLabel', () => {
  it('segundos, minutos y horas', () => {
    expect(agoLabel(5)).toBe('hace 5 s')
    expect(agoLabel(125)).toBe('hace 2 min')
    expect(agoLabel(7300)).toBe('hace 2 h')
  })
})

describe('freshness', () => {
  const ok = { LD: { edad_s: 4, stale: false }, CER: { edad_s: 13, stale: false } }
  it('datos al día', () => {
    expect(freshness(ok, 10_000, 14_000, true)).toEqual({ label: 'hace 4 s', level: 'ok' })
  })
  it('antes de la primera lectura', () => {
    expect(freshness({}, null, 0, true)).toEqual({ label: 'Cargando…', level: 'ok' })
    expect(freshness({}, null, 0, false)).toEqual({ label: 'Sin conexión', level: 'warn' })
  })
  it('sin conexión conserva la edad del último dato', () => {
    expect(freshness(ok, 10_000, 130_000, false)).toEqual({ label: 'Sin conexión · datos de hace 2 min', level: 'warn' })
  })
  it('avisa del feed atrasado', () => {
    const late = { ...ok, LD: { edad_s: 3600, stale: false } }
    expect(freshness(late, 10_000, 14_000, true)).toEqual({
      label: 'Larga y Media Distancia: datos de hace 1 h',
      level: 'warn',
    })
    const stale = { ...ok, CER: { edad_s: 20, stale: true } }
    expect(freshness(stale, 10_000, 14_000, true).label).toBe('Cercanías: datos de hace 20 s')
  })
})
