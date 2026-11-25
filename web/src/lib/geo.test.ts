import { describe, expect, it } from 'vitest'
import type { LngLat } from '../api/types'
import { bounds, circle, distanceLabel, distanceM, interpolate, nearest, splitRoute } from './geo'

const at = (id: string, lon: number, lat: number) => ({ id, lon, lat })

describe('interpolate', () => {
  it('avanza en línea recta entre la posición anterior y la nueva', () => {
    const prev = new Map<string, LngLat>([['a', [0, 0]]])
    const out = interpolate(prev, [at('a', 0.1, 0.2)], 0.5)
    expect(out.get('a')![0]).toBeCloseTo(0.05)
    expect(out.get('a')![1]).toBeCloseTo(0.1)
    expect(interpolate(prev, [at('a', 0.1, 0.2)], 1).get('a')).toEqual([0.1, 0.2])
  })
  it('los trenes nuevos aparecen en su sitio y los que ya no están desaparecen', () => {
    const prev = new Map<string, LngLat>([['viejo', [1, 1]]])
    const out = interpolate(prev, [at('nuevo', 2, 2)], 0.3)
    expect([...out.keys()]).toEqual(['nuevo'])
    expect(out.get('nuevo')).toEqual([2, 2])
  })
  it('un salto grande no se anima', () => {
    const prev = new Map<string, LngLat>([['a', [0, 0]]])
    expect(interpolate(prev, [at('a', 3, 0)], 0.1).get('a')).toEqual([3, 0])
  })
})

describe('splitRoute', () => {
  const shape: LngLat[] = [[0, 0], [1, 0], [2, 0]]
  it('corta en el tramo más cercano al tren', () => {
    expect(splitRoute(shape, [1.4, 0.1])).toEqual({
      done: [[0, 0], [1, 0], [1.4, 0.1]],
      pending: [[1.4, 0.1], [2, 0]],
    })
  })
  it('tren antes del primer vértice', () => {
    expect(splitRoute(shape, [-0.5, 0])).toEqual({
      done: [[0, 0], [-0.5, 0]],
      pending: [[-0.5, 0], [1, 0], [2, 0]],
    })
  })
  it('sin trazado suficiente todo queda pendiente', () => {
    expect(splitRoute([[0, 0]], [5, 5])).toEqual({ done: [], pending: [[0, 0]] })
    expect(splitRoute([], [5, 5])).toEqual({ done: [], pending: [] })
  })
})

describe('bounds', () => {
  it('esquinas suroeste y nordeste', () => {
    expect(bounds([[1, 2], [-3, 5]])).toEqual([[-3, 2], [1, 5]])
    expect(bounds([])).toBeNull()
  })
})

describe('distancias', () => {
  it('distanceM: un grado de latitud son ~111,19 km', () => {
    expect(distanceM([-3.7, 40], [-3.7, 41]) / 1000).toBeCloseTo(111.19, 1)
  })
  it('nearest: filtra por radio, ordena y limita', () => {
    const items = [at('lejos', 1, 0), at('b', 0.01, 0), at('a', 0.001, 0), at('c', 0.02, 0)]
    const out = nearest(items, [0, 0], 5000, 2)
    expect(out.map((i) => i.id)).toEqual(['a', 'b'])
    expect(out[0].dist_m).toBeCloseTo(111, -1)
  })
  it('circle: anillo cerrado al radio pedido', () => {
    const ring = circle([-3.7, 40.4], 1000)
    expect(ring[0]).toEqual(ring[ring.length - 1])
    for (const p of ring) expect(distanceM([-3.7, 40.4], p)).toBeCloseTo(1000, -1)
  })
  it('distanceLabel', () => {
    expect(distanceLabel(350)).toBe('350 m')
    expect(distanceLabel(2345)).toBe('2,3 km')
    expect(distanceLabel(23456)).toBe('23 km')
  })
})
