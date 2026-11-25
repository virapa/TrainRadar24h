import { Map as MlMap, setWorkerUrl } from 'maplibre-gl'
import type { GeoJSONSource, StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Feature, FeatureCollection } from 'geojson'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import type { LngLat, TrainDetail, TrainLight } from '../api/types'
import { category, trainColor } from '../lib/format'
import type { Category } from '../lib/format'
import { bounds, circle, interpolate, splitRoute } from '../lib/geo'
import type { Theme } from '../lib/prefs'

// MapLibre 6 busca su worker junto a su propio módulo, y el empaquetador los separa.
// El plugin "maplibre-worker" de vite.config.ts lo publica en esta ruta.
setWorkerUrl(new URL('/maplibre-gl-worker.js', location.origin).href)

const ANIM_MS = 14_000 // casi lo que tarda en llegar la siguiente lectura (15 s)
const FRAME_MS = 100
const SPAIN_CENTER: LngLat = [-3.7, 40.2]
const ATTRIBUTION = 'Datos: Renfe (CC BY 4.0) · © OpenStreetMap'
const BASE_TILES = ['https://tile.openstreetmap.org/{z}/{x}/{y}.png']

// El tema oscuro son las mismas teselas de OpenStreetMap con la luminosidad invertida y poco color.
type BasePaint = Record<
  'raster-brightness-min' | 'raster-brightness-max' | 'raster-saturation' | 'raster-contrast' | 'raster-hue-rotate',
  number
>
const BASE_PAINT: Record<Theme, BasePaint> = {
  dark: { 'raster-brightness-min': 1, 'raster-brightness-max': 0.12, 'raster-saturation': -0.6, 'raster-contrast': 0.1, 'raster-hue-rotate': 180 },
  light: { 'raster-brightness-min': 0, 'raster-brightness-max': 1, 'raster-saturation': -0.3, 'raster-contrast': 0, 'raster-hue-rotate': 0 },
}

export interface MapHandle {
  fitRoute(): void
  flyTo(point: LngLat, zoom?: number): void
}

interface Props {
  trains: TrainLight[]
  selectedId: string | null
  detail: TrainDetail | null
  follow: boolean
  theme: Theme
  rails: boolean
  me: { pos: LngLat; accuracy: number | null } | null
  onSelect(id: string | null): void
}

function baseStyle(theme: Theme): StyleSpecification {
  return {
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
      base: { type: 'raster', tiles: BASE_TILES, tileSize: 256, maxzoom: 19, attribution: ATTRIBUTION },
      rails: {
        type: 'raster',
        tiles: ['a', 'b', 'c'].map((s) => `https://${s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png`),
        tileSize: 256,
        attribution: '© OpenRailwayMap',
      },
    },
    layers: [
      { id: 'base', type: 'raster', source: 'base', paint: BASE_PAINT[theme] },
      { id: 'rails', type: 'raster', source: 'rails', paint: { 'raster-opacity': 0.55 }, layout: { visibility: 'none' } },
    ],
  }
}

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

function line(coords: LngLat[]): FeatureCollection {
  if (coords.length < 2) return EMPTY
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } }] }
}

function addLayers(map: MlMap, theme: Theme): void {
  for (const id of ['me-accuracy', 'me', 'route-done', 'route-pending', 'route-stops', 'selected', 'trains']) {
    map.addSource(id, { type: 'geojson', data: EMPTY })
  }
  map.addLayer({ id: 'me-accuracy', type: 'fill', source: 'me-accuracy',
                 paint: { 'fill-color': '#4285f4', 'fill-opacity': 0.12, 'fill-outline-color': '#4285f4' } })
  map.addLayer({ id: 'me', type: 'circle', source: 'me',
                 paint: { 'circle-radius': 7, 'circle-color': '#4285f4', 'circle-stroke-width': 3, 'circle-stroke-color': '#ffffff' } })
  map.addLayer({ id: 'route-pending', type: 'line', source: 'route-pending',
                 paint: { 'line-color': '#8ab4f8', 'line-width': 3, 'line-dasharray': [1.5, 1.5] } })
  map.addLayer({ id: 'route-done', type: 'line', source: 'route-done',
                 paint: { 'line-color': '#8ab4f8', 'line-width': 4 } })
  map.addLayer({ id: 'route-stops', type: 'circle', source: 'route-stops',
                 paint: { 'circle-radius': 4, 'circle-stroke-width': 2, 'circle-stroke-color': '#8ab4f8',
                          'circle-color': ['match', ['get', 'estado'], 'pasada', '#8ab4f8', 'suprimida', '#f28b82', '#10151c'] } })
  map.addLayer({ id: 'selected', type: 'circle', source: 'selected',
                 paint: { 'circle-radius': 20, 'circle-color': 'rgba(138,180,248,0.25)',
                          'circle-stroke-width': 2, 'circle-stroke-color': '#8ab4f8' } })
  map.addLayer({
    id: 'trains', type: 'symbol', source: 'trains',
    layout: {
      'icon-image': ['get', 'icon'],
      'icon-rotate': ['get', 'rumbo'],
      'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
      'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.6, 10, 0.95, 14, 1.3],
      'text-field': ['step', ['zoom'], '', 9, ['get', 'label']],
      'text-font': ['Open Sans Semibold'],
      'text-size': 11,
      'text-offset': [0, 1.5],
      'text-optional': true,
    },
    paint: {
      'text-color': theme === 'dark' ? '#e8eaed' : '#202124',
      'text-halo-color': theme === 'dark' ? '#10151c' : '#ffffff',
      'text-halo-width': 1.4,
    },
  })
}

/** Silueta del tren vista desde arriba, con el morro hacia arriba (64×64). */
function silhouette(g: CanvasRenderingContext2D, cat: Category): void {
  g.beginPath()
  if (cat === 'ave') {
    // Alta velocidad: larga, estrecha y con morro afilado.
    g.moveTo(32, 2)
    g.bezierCurveTo(40, 12, 42, 22, 42, 30)
    g.lineTo(42, 58)
    g.quadraticCurveTo(42, 62, 38, 62)
    g.lineTo(26, 62)
    g.quadraticCurveTo(22, 62, 22, 58)
    g.lineTo(22, 30)
    g.bezierCurveTo(22, 22, 24, 12, 32, 2)
  } else if (cat === 'ld') {
    // Larga distancia convencional: larga, con morro redondeado y algo más ancha.
    g.moveTo(21, 22)
    g.bezierCurveTo(21, 10, 27, 3, 32, 3)
    g.bezierCurveTo(37, 3, 43, 10, 43, 22)
    g.lineTo(43, 58)
    g.quadraticCurveTo(43, 62, 39, 62)
    g.lineTo(25, 62)
    g.quadraticCurveTo(21, 62, 21, 58)
  } else if (cat === 'md') {
    // Media distancia: cabina redondeada.
    g.moveTo(20, 20)
    g.bezierCurveTo(20, 8, 26, 4, 32, 4)
    g.bezierCurveTo(38, 4, 44, 8, 44, 20)
    g.lineTo(44, 58)
    g.quadraticCurveTo(44, 61, 41, 61)
    g.lineTo(23, 61)
    g.quadraticCurveTo(20, 61, 20, 58)
  } else {
    // Cercanías: corta, ancha y de frente casi plano.
    g.moveTo(19, 14)
    g.quadraticCurveTo(19, 8, 25, 8)
    g.lineTo(39, 8)
    g.quadraticCurveTo(45, 8, 45, 14)
    g.lineTo(45, 54)
    g.quadraticCurveTo(45, 58, 41, 58)
    g.lineTo(23, 58)
    g.quadraticCurveTo(19, 58, 19, 54)
  }
  g.closePath()
}

/** Dibuja el icono de un tren según su categoría (un punto si no hay rumbo) y lo registra en el mapa. */
function ensureIcon(map: MlMap, color: string, cat: Category, arrow: boolean): string {
  const name = `${arrow ? cat : 'dot'}-${color}`
  if (map.hasImage(name)) return name
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const g = canvas.getContext('2d')
  if (!g) return name
  g.lineJoin = 'round'
  g.lineWidth = 4
  g.strokeStyle = '#ffffff'
  g.fillStyle = color
  if (arrow) {
    silhouette(g, cat)
    g.stroke()
    g.fill()
    // Parabrisas y franja central, para que se lea como un tren y se vea hacia dónde mira.
    g.fillStyle = 'rgba(16,21,28,0.85)'
    g.beginPath()
    if (cat === 'ave') {
      g.moveTo(32, 14)
      g.lineTo(38, 26)
      g.lineTo(26, 26)
    } else if (cat === 'ld') {
      g.roundRect(25, 11, 14, 8, 4)
    } else if (cat === 'md') {
      g.roundRect(24, 12, 16, 9, 3)
    } else {
      g.roundRect(23, 13, 18, 8, 2)
    }
    g.closePath()
    g.fill()
    g.fillStyle = 'rgba(255,255,255,0.55)'
    g.fillRect(30.5, 30, 3, 24)
  } else {
    g.beginPath()
    g.arc(32, 32, 15, 0, Math.PI * 2)
    g.stroke()
    g.fill()
  }
  map.addImage(name, g.getImageData(0, 0, size, size), { pixelRatio: 2 })
  return name
}

function setData(map: MlMap, source: string, data: FeatureCollection): void {
  (map.getSource(source) as GeoJSONSource | undefined)?.setData(data)
}

export const MapView = forwardRef<MapHandle, Props>(function MapView(props, ref) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const [ready, setReady] = useState(false)
  const shown = useRef(new Map<string, LngLat>()) // posición que se está pintando de cada tren
  const latest = useRef(props)
  latest.current = props

  const draw = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    const { trains, selectedId, follow } = latest.current
    const features: Feature[] = []
    for (const t of trains) {
      const pos = shown.current.get(t.id)
      if (!pos) continue
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: pos },
        properties: { id: t.id, label: t.numero, rumbo: t.rumbo ?? 0, icon: ensureIcon(map, trainColor(t), category(t.servicio), t.rumbo !== null) },
      })
    }
    setData(map, 'trains', { type: 'FeatureCollection', features })
    const sel = selectedId ? shown.current.get(selectedId) : undefined
    setData(map, 'selected', sel
      ? { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: sel } }] }
      : EMPTY)
    if (sel && follow) map.easeTo({ center: sel, duration: FRAME_MS * 2 })
  }, [])

  // Crear el mapa una sola vez.
  useEffect(() => {
    if (!container.current) return
    const map = new MlMap({
      container: container.current,
      style: baseStyle(latest.current.theme),
      center: SPAIN_CENTER,
      zoom: 5.3,
      dragRotate: false,
      pitchWithRotate: false,
      attributionControl: { compact: true },
    })
    map.touchZoomRotate.disableRotation()
    mapRef.current = map
    map.on('load', () => {
      if (mapRef.current !== map) return // mapa ya destruido (StrictMode monta, limpia y vuelve a montar)
      addLayers(map, latest.current.theme)
      setReady(true)
    })
    map.on('click', (e) => {
      const pad = 10 // margen para dedos
      const hits = map.queryRenderedFeatures(
        [[e.point.x - pad, e.point.y - pad], [e.point.x + pad, e.point.y + pad]],
        { layers: ['trains'] },
      )
      latest.current.onSelect((hits[0]?.properties?.id as string | undefined) ?? null)
    })
    return () => {
      map.remove()
      mapRef.current = null
      setReady(false)
    }
  }, [])

  // Animar de la posición pintada a la nueva lectura.
  useEffect(() => {
    if (!ready) return
    const from = new Map(shown.current)
    const start = performance.now()
    let raf = 0
    let last = 0
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / ANIM_MS)
      if (now - last >= FRAME_MS || t === 1) {
        last = now
        shown.current = interpolate(from, props.trains, from.size ? t : 1)
        draw()
      }
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [props.trains, ready, draw])

  // Redibujar al cambiar la selección o el modo seguir.
  useEffect(() => {
    if (ready) draw()
  }, [props.selectedId, props.follow, ready, draw])

  // Recorrido del tren seleccionado: tramo hecho, tramo pendiente y paradas.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const d = props.detail
    if (!d) {
      for (const id of ['route-done', 'route-pending', 'route-stops']) setData(map, id, EMPTY)
      return
    }
    const pos = shown.current.get(d.id) ?? [d.lon, d.lat]
    const { done, pending } = splitRoute(d.shape, pos)
    setData(map, 'route-done', line(done))
    setData(map, 'route-pending', line(pending))
    setData(map, 'route-stops', {
      type: 'FeatureCollection',
      features: d.paradas
        .filter((p) => p.lat !== null && p.lon !== null)
        .map((p) => ({ type: 'Feature', properties: { estado: p.estado },
                       geometry: { type: 'Point', coordinates: [p.lon as number, p.lat as number] } })),
    })
  }, [props.detail, ready])

  // Tema: cambiar el tratamiento de color del mapa base y el color de las etiquetas.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const paint = BASE_PAINT[props.theme]
    for (const key of Object.keys(paint) as (keyof BasePaint)[]) map.setPaintProperty('base', key, paint[key])
    map.setPaintProperty('trains', 'text-color', props.theme === 'dark' ? '#e8eaed' : '#202124')
    map.setPaintProperty('trains', 'text-halo-color', props.theme === 'dark' ? '#10151c' : '#ffffff')
  }, [props.theme, ready])

  // Posición del usuario y círculo de precisión.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const me = props.me
    setData(map, 'me', me
      ? { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: me.pos } }] }
      : EMPTY)
    setData(map, 'me-accuracy', me && me.accuracy && me.accuracy > 30
      ? { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {},
          geometry: { type: 'Polygon', coordinates: [circle(me.pos, Math.min(me.accuracy, 5000))] } }] }
      : EMPTY)
  }, [props.me, ready])

  // Capa de vías.
  useEffect(() => {
    if (ready) mapRef.current?.setLayoutProperty('rails', 'visibility', props.rails ? 'visible' : 'none')
  }, [props.rails, ready])

  useImperativeHandle(ref, () => ({
    fitRoute() {
      const d = latest.current.detail
      const box = d ? bounds(d.shape) : null
      if (box) mapRef.current?.fitBounds(box, { padding: { top: 90, bottom: 320, left: 40, right: 40 }, maxZoom: 12 })
    },
    flyTo(point, zoom = 12) {
      mapRef.current?.flyTo({ center: point, zoom })
    },
  }), [])

  return <div ref={container} className="map" />
})
