import { useCallback, useEffect, useState } from 'react'
import type { Route } from '../lib/route'
import { buildPath, parsePath } from '../lib/route'

/** Ruta actual según la URL, con navegación mediante el historial del navegador. */
export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parsePath(location.pathname))

  useEffect(() => {
    const onPop = () => setRoute(parsePath(location.pathname))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((next: Route) => {
    const path = buildPath(next)
    if (path !== location.pathname) history.pushState(null, '', path)
    setRoute(next)
  }, [])

  return { route, navigate }
}
