import { describe, expect, it } from 'vitest'
import { urlBase64ToUint8Array } from './push'

describe('urlBase64ToUint8Array', () => {
  it('decodifica base64 normal', () => {
    expect([...urlBase64ToUint8Array('AQID')]).toEqual([1, 2, 3])
  })
  it('admite el alfabeto de URL y la falta de relleno', () => {
    expect([...urlBase64ToUint8Array('-_8')]).toEqual([251, 255])
  })
  it('una clave VAPID pública ocupa 65 bytes', () => {
    const key = 'BDRSaZXOLUqzm4qh9aQy8koZlxE_gb1ArfQrVNDNK40TanS5JXeBzkhrLZHcvi0XLVU0xCilIBqgftwyl3923sM'
    expect(urlBase64ToUint8Array(key)).toHaveLength(65)
  })
})
