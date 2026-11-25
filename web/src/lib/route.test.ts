import { describe, expect, it } from 'vitest'
import { buildPath, parsePath } from './route'

describe('parsePath', () => {
  it('mapa', () => {
    expect(parsePath('/')).toEqual({ kind: 'map' })
    expect(parsePath('/cualquier/otra')).toEqual({ kind: 'map' })
    expect(parsePath('/t/')).toEqual({ kind: 'map' })
  })
  it('tren, con o sin codificar los dos puntos', () => {
    expect(parsePath('/t/LD:03304')).toEqual({ kind: 'train', id: 'LD:03304' })
    expect(parsePath('/t/LD%3A03304')).toEqual({ kind: 'train', id: 'LD:03304' })
  })
  it('estación', () => {
    expect(parsePath('/s/60000')).toEqual({ kind: 'station', id: '60000' })
  })
})

describe('buildPath', () => {
  it('es la inversa de parsePath', () => {
    expect(buildPath({ kind: 'map' })).toBe('/')
    expect(buildPath({ kind: 'train', id: 'LD:03304' })).toBe('/t/LD:03304')
    expect(buildPath({ kind: 'station', id: '60000' })).toBe('/s/60000')
    expect(parsePath(buildPath({ kind: 'train', id: 'CER:35903' }))).toEqual({ kind: 'train', id: 'CER:35903' })
  })
})
