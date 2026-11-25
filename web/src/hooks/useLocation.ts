import { useCallback, useEffect, useRef, useState } from 'react'
import type { LngLat } from '../api/types'

export type LocationStatus = 'idle' | 'waiting' | 'ok' | 'denied' | 'unsupported' | 'error'

export interface Location {
  pos: LngLat | null
  accuracy: number | null // metros
  status: LocationStatus
}

const ASKED_KEY = 'tr24.geoAsked'

function supported(): boolean {
  return 'geolocation' in navigator && window.isSecureContext
}

/**
 * Posición del usuario. La primera vez que se abre la app pide permiso; si ya se concedió, empieza a
 * seguir la posición sin preguntar. Si se denegó, no vuelve a molestar hasta que se pulse el botón.
 */
export function useLocation(): Location & { start(): void } {
  const [loc, setLoc] = useState<Location>({ pos: null, accuracy: null, status: supported() ? 'idle' : 'unsupported' })
  const watch = useRef<number | null>(null)

  const start = useCallback(() => {
    if (!supported()) {
      setLoc((l) => ({ ...l, status: 'unsupported' }))
      return
    }
    try { localStorage.setItem(ASKED_KEY, '1') } catch { /* almacenamiento bloqueado */ }
    if (watch.current !== null) return
    setLoc((l) => (l.pos ? l : { ...l, status: 'waiting' }))
    watch.current = navigator.geolocation.watchPosition(
      (p) => setLoc({ pos: [p.coords.longitude, p.coords.latitude], accuracy: p.coords.accuracy, status: 'ok' }),
      (err) => {
        if (watch.current !== null) navigator.geolocation.clearWatch(watch.current)
        watch.current = null
        setLoc((l) => ({ ...l, status: err.code === err.PERMISSION_DENIED ? 'denied' : 'error' }))
      },
      { enableHighAccuracy: true, maximumAge: 15_000, timeout: 20_000 },
    )
  }, [])

  useEffect(() => {
    if (!supported()) return
    let asked = false
    try { asked = localStorage.getItem(ASKED_KEY) === '1' } catch { /* almacenamiento bloqueado */ }
    const decide = (state: PermissionState | null) => {
      if (state === 'granted' || (state !== 'denied' && !asked)) start()
      else if (state === 'denied') setLoc((l) => ({ ...l, status: 'denied' }))
    }
    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: 'geolocation' }).then((s) => decide(s.state), () => decide(null))
    } else {
      decide(null)
    }
    return () => {
      if (watch.current !== null) navigator.geolocation.clearWatch(watch.current)
      watch.current = null
    }
  }, [start])

  return { ...loc, start }
}
