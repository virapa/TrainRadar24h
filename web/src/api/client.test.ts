import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, deleteFavorite, deviceId, getBoard, getTrain, getTrains, putFavorite, saveSubscription,
         search, stationsNear } from './client'

const fetchMock = vi.fn()

function json(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' }, ...init })
}

beforeEach(() => {
  localStorage.clear()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe('deviceId', () => {
  it('se genera una vez y se conserva', () => {
    const id = deviceId()
    expect(id.length).toBeGreaterThanOrEqual(8)
    expect(deviceId()).toBe(id)
  })
})

describe('getTrains', () => {
  it('primera lectura: devuelve los datos y el ETag', async () => {
    fetchMock.mockResolvedValue(json({ trenes: [], feeds: {}, generado: 1 }, { headers: { ETag: '"abc"' } }))
    const r = await getTrains(null)
    expect(fetchMock).toHaveBeenCalledWith('/api/trains', { headers: {} })
    expect(r).toEqual({ data: { trenes: [], feeds: {}, generado: 1 }, etag: '"abc"' })
  })
  it('con ETag: envía If-None-Match y trata el 304 como "sin cambios"', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 304 }))
    const r = await getTrains('"abc"')
    expect(fetchMock).toHaveBeenCalledWith('/api/trains', { headers: { 'If-None-Match': '"abc"' } })
    expect(r).toEqual({ data: null, etag: '"abc"' })
  })
  it('un error del servidor lanza ApiError con el código', async () => {
    fetchMock.mockResolvedValue(new Response('fallo', { status: 500 }))
    await expect(getTrains(null)).rejects.toMatchObject({ status: 500 })
    await expect(getTrains(null)).rejects.toBeInstanceOf(ApiError)
  })
})

describe('lecturas', () => {
  it('codifica el id del tren', async () => {
    fetchMock.mockResolvedValue(json({ id: 'LD:03304' }))
    await getTrain('LD:03304')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/trains/LD%3A03304')
  })
  it('búsqueda, estaciones cercanas y panel', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json({})))
    await search('puerta de atocha')
    await stationsNear(40.4, -3.7)
    await getBoard('60000', 'llegadas')
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      '/api/search?q=puerta%20de%20atocha',
      '/api/stations/near?lat=40.4&lon=-3.7',
      '/api/stations/60000/board?tipo=llegadas',
    ])
  })
})

describe('escrituras del dispositivo', () => {
  it('putFavorite envía el id de dispositivo y el cuerpo', async () => {
    fetchMock.mockResolvedValue(json({ ok: true }))
    await putFavorite({ tipo: 'tren', ref: '03304' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/favorites')
    expect(init.method).toBe('PUT')
    expect(init.headers['X-Device-Id']).toBe(deviceId())
    expect(JSON.parse(init.body)).toEqual({ tipo: 'tren', ref: '03304' })
  })
  it('deleteFavorite usa parámetros de consulta', async () => {
    fetchMock.mockResolvedValue(json({ ok: true }))
    await deleteFavorite('estacion', '60000')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/favorites?tipo=estacion&ref=60000')
    expect(init.method).toBe('DELETE')
  })
  it('saveSubscription hace POST', async () => {
    fetchMock.mockResolvedValue(json({ ok: true }))
    await saveSubscription({ endpoint: 'https://push.example.test/x', keys: { p256dh: 'k', auth: 'a' } })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/push/subscription')
    expect(init.method).toBe('POST')
  })
})
