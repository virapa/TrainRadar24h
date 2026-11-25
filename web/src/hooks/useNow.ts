import { useEffect, useState } from 'react'

/** Hora actual en ms, refrescada cada intervalMs. Sirve para textos del tipo "hace 12 s". */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
  return now
}
