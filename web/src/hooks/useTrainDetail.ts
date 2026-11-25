import { useEffect, useState } from 'react'
import { ApiError, getTrain } from '../api/client'
import type { TrainDetail } from '../api/types'

const POLL_MS = 15_000

/** Ficha del tren seleccionado, releída cada 15 s. gone: el tren ya no está en circulación (404). */
export function useTrainDetail(id: string | null) {
  const [detail, setDetail] = useState<TrainDetail | null>(null)
  const [gone, setGone] = useState(false)

  useEffect(() => {
    setDetail(null)
    setGone(false)
    if (!id) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const tick = async () => {
      try {
        const next = await getTrain(id)
        if (stopped) return
        setDetail(next)
        setGone(false)
      } catch (err) {
        if (stopped) return
        if (err instanceof ApiError && err.status === 404) {
          setDetail(null)
          setGone(true)
        }
        // Otros fallos (red): se conserva la última ficha y se reintenta.
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS)
    }

    void tick()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [id])

  return { detail, gone }
}
