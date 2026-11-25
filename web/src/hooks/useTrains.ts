import { useEffect, useState } from 'react'
import { getTrains } from '../api/client'
import type { TrainsResponse } from '../api/types'

const POLL_MS = 15_000
const CACHE_KEY = 'tr24.trains'

function loadCached(): TrainsResponse | null {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) ?? 'null') as TrainsResponse | null
  } catch {
    return null
  }
}

/**
 * Lista de trenes, releída cada 15 s con ETag.
 * resp: última respuesta (al arrancar, la guardada de la sesión anterior).
 * checkedAt: ms de la última lectura correcta en esta sesión, o null.
 * online: false si la última lectura falló.
 */
export function useTrains() {
  const [resp, setResp] = useState<TrainsResponse | null>(loadCached)
  const [checkedAt, setCheckedAt] = useState<number | null>(null)
  const [online, setOnline] = useState(true)

  useEffect(() => {
    let etag: string | null = null
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const tick = async () => {
      try {
        const result = await getTrains(etag)
        if (stopped) return
        etag = result.etag
        if (result.data) {
          setResp(result.data)
          try {
            localStorage.setItem(CACHE_KEY, JSON.stringify(result.data))
          } catch {
            // Sin espacio en localStorage: se sigue sin caché.
          }
        }
        setCheckedAt(Date.now())
        setOnline(true)
      } catch {
        if (!stopped) setOnline(false)
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS)
    }

    void tick()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [])

  return { resp, checkedAt, online }
}
