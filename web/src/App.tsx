import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { TrainLight } from './api/types'
import { FavoritesPanel } from './components/FavoritesPanel'
import { FiltersPanel } from './components/FiltersPanel'
import type { MapHandle } from './components/MapView'
import { MapView } from './components/MapView'
import { NearbyPanel } from './components/NearbyPanel'
import { SearchPanel } from './components/SearchPanel'
import { StationBoard } from './components/StationBoard'
import { TrainSheet } from './components/TrainSheet'
import { useFavorites } from './hooks/useFavorites'
import { useLocation } from './hooks/useLocation'
import { useNow } from './hooks/useNow'
import { useRoute } from './hooks/useRoute'
import { useTrainDetail } from './hooks/useTrainDetail'
import { useTrains } from './hooks/useTrains'
import type { Filters } from './lib/filters'
import { applyFilters, loadFilters, saveFilters } from './lib/filters'
import type { Category } from './lib/format'
import { category, freshness } from './lib/format'
import type { Prefs } from './lib/prefs'
import { loadPrefs, savePrefs } from './lib/prefs'

type Panel = 'search' | 'filters' | 'favorites' | 'nearby' | null

const NO_TRAINS: TrainLight[] = []

export default function App() {
  const { route, navigate } = useRoute()
  const { resp, checkedAt, online } = useTrains()
  const now = useNow(1000)
  const favorites = useFavorites()
  const [filters, setFilters] = useState<Filters>(loadFilters)
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs)
  const [panel, setPanel] = useState<Panel>(null)
  const [follow, setFollow] = useState(false)
  const [toast, setToast] = useState('')
  const mapRef = useRef<MapHandle>(null)
  const location = useLocation()
  const flyPending = useRef(false)

  const all = resp?.trenes ?? NO_TRAINS
  const selectedId = route.kind === 'train' ? route.id : null
  const { detail, gone } = useTrainDetail(selectedId)

  // El tren seleccionado se pinta siempre, aunque los filtros lo oculten.
  const visible = useMemo(() => {
    const filtered = applyFilters(all, filters)
    if (!selectedId || filtered.some((t) => t.id === selectedId)) return filtered
    const selected = all.find((t) => t.id === selectedId)
    return selected ? [...filtered, selected] : filtered
  }, [all, filters, selectedId])

  const counts = useMemo(() => {
    const out: Record<Category, number> = { ave: 0, ld: 0, md: 0, cer: 0 }
    for (const t of all) out[category(t.servicio)]++
    return out
  }, [all])

  useEffect(() => {
    document.documentElement.dataset.theme = prefs.theme
  }, [prefs.theme])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(''), 4000)
    return () => clearTimeout(timer)
  }, [toast])

  const selectTrain = useCallback((id: string | null) => {
    setFollow(false)
    setPanel(null)
    navigate(id ? { kind: 'train', id } : { kind: 'map' })
  }, [navigate])

  const openStation = useCallback((id: string) => {
    setPanel(null)
    navigate({ kind: 'station', id })
  }, [navigate])

  const changeFilters = (next: Filters) => {
    setFilters(next)
    saveFilters(next)
  }

  const changePrefs = (next: Prefs) => {
    setPrefs(next)
    savePrefs(next)
  }

  // «Cerca de ti»: pide la ubicación si aún no la hay y centra el mapa en cuanto llega.
  const { pos } = location
  const locate = () => {
    setPanel('nearby')
    if (pos) mapRef.current?.flyTo(pos, 12)
    else flyPending.current = true
    location.start()
  }
  useEffect(() => {
    if (pos && flyPending.current) {
      flyPending.current = false
      mapRef.current?.flyTo(pos, 12)
    }
  }, [pos])

  const me = useMemo(() => (pos ? { pos, accuracy: location.accuracy } : null), [pos, location.accuracy])

  const fresh = freshness(resp?.feeds ?? {}, checkedAt, now, online)
  const filtersActive = !filters.ave || !filters.ld || !filters.md || !filters.cer || filters.soloRetraso

  return (
    <div className="app">
      <MapView ref={mapRef} trains={visible} selectedId={selectedId} detail={detail} follow={follow}
               theme={prefs.theme} rails={prefs.rails} me={me} onSelect={selectTrain} />

      <header className="topbar">
        <button className="searchbox" onClick={() => setPanel('search')}>Buscar tren o estación</button>
        <span className={`fresh ${fresh.level}`} role="status">{fresh.label}</span>
      </header>

      {!selectedId && (
        <nav className="bottombar">
          <button onClick={() => setPanel('filters')}>Filtros{filtersActive ? ' •' : ''}</button>
          <button onClick={() => setPanel('favorites')}>Favoritos</button>
          <button onClick={locate}>Cerca de ti</button>
          <span className="count">{visible.length} trenes</span>
        </nav>
      )}

      {selectedId && (
        <TrainSheet detail={detail} gone={gone}
                    favorite={detail ? favorites.has('tren', detail.numero) : false}
                    following={follow}
                    onClose={() => selectTrain(null)}
                    onFavorite={(numero) => void favorites.toggle('tren', numero)}
                    onFollow={() => setFollow((f) => !f)}
                    onRoute={() => { setFollow(false); mapRef.current?.fitRoute() }}
                    onStation={openStation} />
      )}

      {route.kind === 'station' && (
        <StationBoard stationId={route.id} favorite={favorites.has('estacion', route.id)}
                      onClose={() => navigate({ kind: 'map' })}
                      onFavorite={() => void favorites.toggle('estacion', route.id)}
                      onTrain={selectTrain} />
      )}

      {panel === 'search' && <SearchPanel onClose={() => setPanel(null)} onTrain={selectTrain} onStation={openStation} />}
      {panel === 'filters' && (
        <FiltersPanel filters={filters} prefs={prefs} counts={counts} onFilters={changeFilters}
                      onPrefs={changePrefs} onClose={() => setPanel(null)} />
      )}
      {panel === 'favorites' && (
        <FavoritesPanel favorites={favorites.list} trains={all}
                        onAvisos={(fav, avisos) => void favorites.setAvisos(fav, avisos)}
                        onRemove={(tipo, ref) => void favorites.toggle(tipo, ref)}
                        onTrain={selectTrain} onStation={openStation} onClose={() => setPanel(null)} />
      )}

      {panel === 'nearby' && (
        <NearbyPanel location={location} trains={visible} onRetry={location.start}
                     onTrain={selectTrain} onStation={openStation} onClose={() => setPanel(null)} />
      )}

      {toast && <div className="toast" role="alert">{toast}</div>}
    </div>
  )
}
