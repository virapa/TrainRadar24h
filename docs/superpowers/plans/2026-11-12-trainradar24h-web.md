# TrainRadar24h · PWA (web) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PWA instalable que muestra en un mapa los trenes de Renfe en vivo, con ficha del tren, búsqueda, panel de estación, filtros, favoritos y avisos push, consumiendo la API ya desplegada.

**Architecture:** Aplicación React de una sola página. La lógica pura (formato, filtros, geometría, rutas, cliente HTTP) vive en módulos sin React y se prueba con Vitest. Los componentes solo pintan. El mapa es MapLibre GL con teselas ráster; los trenes son una capa de símbolos que se anima entre lecturas. En producción la sirve nginx, que además hace de proxy de `/api` hacia el contenedor de la API.

**Tech Stack:** Vite, React, TypeScript, MapLibre GL JS, Vitest (jsdom), service worker escrito a mano, nginx, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-11-trainradar24h-mvp-design.md` (§6 Pantallas, §7 Avisos push)

**Estado de partida:** la API corre en Docker en `http://localhost:8090` (servicio `api` de `docker-compose.yml`, puerto interno 8000). En este equipo los puertos 8000, 8080 y 5173 están ocupados por otros proyectos: **no tocar esos contenedores**.

**Convenciones:**
- Todos los comandos se ejecutan desde `web/` salvo que se indique otra cosa.
- Posiciones como `[lon, lat]` (orden de MapLibre y GeoJSON).
- El código cumple las opciones estrictas de la plantilla de Vite: `import type` para tipos, sin `enum`, sin propiedades declaradas en parámetros de constructor, sin variables sin usar.
- Textos de la interfaz en español.
- Verificación: cada tarea termina con `npm test` y `npm run build` en verde. La comprobación visual en navegador la hace el coordinador en las tareas 12 y 13, no los agentes de cada tarea.

**Contrato de la API (ya implementado, no cambiar):**

| Ruta | Respuesta |
|---|---|
| `GET /api/trains` | `{trenes: TrainLight[], feeds: {LD|CER: {edad_s, stale}}, generado}` · cabecera `ETag`; con `If-None-Match` igual devuelve 304 |
| `GET /api/trains/{id}` | `TrainDetail` (tren completo + `paradas[]` + `shape: [lon,lat][]`) · 404 si ya no circula |
| `GET /api/search?q=` | `{trenes: TrainLight[], estaciones: Station[]}` (solo dígitos → trenes; texto → estaciones) |
| `GET /api/stations/near?lat=&lon=` | `Station[]` con `dist_m` |
| `GET /api/stations/{id}/board?tipo=salidas\|llegadas` | `{estacion, tipo, filas: BoardRow[]}` |
| `GET/PUT/DELETE /api/favorites` | cabecera `X-Device-Id` (8–64 caracteres). PUT: `{tipo, ref, avisos?}`. DELETE: `?tipo=&ref=`. El favorito de tren usa como `ref` el **número** del tren |
| `GET /api/push/vapid-public-key` | `{key}` (cadena vacía si no está configurado) |
| `POST/DELETE /api/push/subscription` | cabecera `X-Device-Id`. POST: `{endpoint, keys: {p256dh, auth}}` |

El aviso push llega al service worker como JSON `{title, body, url, tag}`; `url` es `/t/<id del tren>` o `/`.

**Desviaciones del spec (deliberadas):**
- Filtro de Cercanías sin desglose por núcleo: la API no expone el núcleo.
- La etiqueta con el número del tren se muestra a partir de zoom 9 (el spec decía zoom ≥ 10 o menos de 150 trenes visibles).
- Color de los trenes: por categoría para Larga y Media Distancia (Renfe publica el mismo gris `#F2F5F5` para todos) y el color de la línea para Cercanías.
- Mapa base de CARTO (oscuro y claro) sobre datos de OpenStreetMap, en lugar de las teselas de OSM, porque ofrece variante oscura.

## Estructura de ficheros

```
web/
├─ package.json, vite.config.ts, index.html, tsconfig*.json   (plantilla de Vite, ajustada)
├─ Dockerfile, nginx.conf, .dockerignore
├─ scripts/make_icons.py            genera los iconos PNG de la PWA
├─ public/
│  ├─ manifest.webmanifest
│  ├─ sw.js                         service worker: caché de la app y avisos push
│  └─ icon-192.png, icon-512.png
└─ src/
   ├─ main.tsx                      arranque y registro del service worker
   ├─ App.tsx                       estado global y composición de pantallas
   ├─ styles.css
   ├─ api/
   │  ├─ types.ts                   tipos del contrato de la API
   │  └─ client.ts                  llamadas HTTP, ETag, id de dispositivo
   ├─ lib/
   │  ├─ format.ts                  categoría, color, retraso, frescura
   │  ├─ filters.ts                 filtros y su persistencia
   │  ├─ geo.ts                     interpolación, corte de ruta, límites
   │  ├─ route.ts                   /t/<id> y /s/<id>
   │  ├─ prefs.ts                   tema y capa de vías
   │  └─ push.ts                    alta y baja de avisos push
   ├─ hooks/
   │  ├─ useRoute.ts, useNow.ts
   │  ├─ useTrains.ts               sondeo de la lista cada 15 s
   │  ├─ useTrainDetail.ts          sondeo de la ficha
   │  └─ useFavorites.ts
   └─ components/
      ├─ MapView.tsx                mapa, capa de trenes, animación, ruta
      ├─ TrainSheet.tsx             ficha en dos niveles
      ├─ SearchPanel.tsx
      ├─ StationBoard.tsx
      ├─ FiltersPanel.tsx
      └─ FavoritesPanel.tsx
```

---

### Task 1: Esqueleto del proyecto web

**Files:**
- Create: `web/` (plantilla de Vite), `web/vite.config.ts`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles.css`, `web/index.html`
- Delete: `web/src/App.css`, `web/src/index.css`, `web/src/assets/`, `web/public/vite.svg`

- [ ] **Step 1: Crear el proyecto** (desde la raíz del repo)

```bash
npm create vite@latest web -- --template react-ts
```
```bash
cd web && npm install && npm install maplibre-gl && npm install -D vitest jsdom @types/geojson @types/node
```
(`@types/node` hace falta para usar `process.env` en `vite.config.ts`; si la plantilla ya lo trae, npm lo deja como está.)

- [ ] **Step 2: Limpiar la plantilla**

Borrar `src/App.css`, `src/index.css`, la carpeta `src/assets/` y `public/vite.svg`.

- [ ] **Step 3: `vite.config.ts`**

```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// En desarrollo, /api se reenvía a la API que corre en Docker.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8090' },
  },
  test: { environment: 'jsdom' },
})
```

- [ ] **Step 4: `index.html`** (sustituir entero)

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#10151c" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="icon" href="/icon-192.png" />
    <link rel="apple-touch-icon" href="/icon-192.png" />
    <title>TrainRadar24h</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: `src/main.tsx`, `src/App.tsx` y `src/styles.css` provisionales**

`src/main.tsx`:
```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

`src/App.tsx`:
```tsx
export default function App() {
  return <p>TrainRadar24h</p>
}
```

`src/styles.css`:
```css
html, body, #root { height: 100%; margin: 0; }
```

- [ ] **Step 6: Scripts de `package.json`**

En `"scripts"`, añadir `"test": "vitest run"` y dejar `"build": "tsc -b && vite build"` como viene en la plantilla.

- [ ] **Step 7: Verificar**

Run: `npm run build`
Expected: termina sin errores y crea `dist/index.html`.

Run: `npm test`
Expected: Vitest termina con "No test files found" y código de salida distinto de 0. Es lo esperado en esta tarea (aún no hay pruebas).

- [ ] **Step 8: Commit** (desde la raíz)

```bash
git add web
git commit -m "feat(web): esqueleto Vite + React + TypeScript con Vitest y proxy a la API"
```
(`node_modules/` y `dist/` ya están en el `.gitignore` de la raíz.)

---

### Task 2: Tipos de la API y formato (`format.ts`)

**Files:**
- Create: `web/src/api/types.ts`, `web/src/lib/format.ts`
- Test: `web/src/lib/format.test.ts`

- [ ] **Step 1: Tipos** — `src/api/types.ts`

```ts
export interface TrainLight {
  id: string
  numero: string
  servicio: string
  linea: string | null
  color: string
  lat: number
  lon: number
  rumbo: number | null
  retraso_min: number | null
  estado: string
}

export interface FeedInfo {
  edad_s: number
  stale: boolean
}

export type Feeds = Record<string, FeedInfo>

export interface TrainsResponse {
  trenes: TrainLight[]
  feeds: Feeds
  generado: number
}

export type StopState = 'pasada' | 'proxima' | 'pendiente' | 'suprimida'

export interface Parada {
  id: string
  nombre: string
  lat: number | null
  lon: number | null
  ts_prog: number
  ts_est: number
  hora_prog: string
  hora_est: string
  retraso_s: number
  estado: StopState
}

export interface NextStop {
  id: string
  nombre: string
  hora_prog: string
  hora_est: string
}

export type LngLat = [number, number]

export interface TrainDetail extends TrainLight {
  source: 'LD' | 'CER'
  trip_id: string
  fecha: string
  origen: string | null
  destino: string | null
  proxima_parada: NextStop | null
  anden: string | null
  progreso: number | null
  casado_con_horario: boolean
  cancelado: boolean
  ts: number
  paradas: Parada[]
  shape: LngLat[]
}

export interface Station {
  id: string
  nombre: string
  lat: number
  lon: number
  dist_m?: number
}

export interface SearchResponse {
  trenes: TrainLight[]
  estaciones: Station[]
}

export type BoardKind = 'salidas' | 'llegadas'

export interface BoardRow {
  ts_prog: number
  hora_prog: string
  hora_est: string
  retraso_min: number | null
  origen: string
  destino: string
  servicio: string
  linea: string | null
  numero: string
  anden: string | null
  estado: 'programado' | 'en_circulacion' | 'cancelado' | 'suprimida'
  train_id: string | null
}

export interface BoardResponse {
  estacion: Station
  tipo: BoardKind
  filas: BoardRow[]
}

export interface Avisos {
  retraso: boolean
  cancelacion: boolean
  anden: boolean
  salida: boolean
}

export type FavoriteKind = 'tren' | 'estacion'

export interface Favorite {
  tipo: FavoriteKind
  ref: string
  avisos: Avisos
}
```

- [ ] **Step 2: Test que falla** — `src/lib/format.test.ts`

```ts
import { describe, expect, it } from 'vitest'
import { agoLabel, category, delayLabel, delayLevel, freshness, trainColor, trainTitle } from './format'

describe('category', () => {
  it('clasifica los servicios reales de Renfe', () => {
    expect(category('AVE')).toBe('avld')
    expect(category('ALVIA')).toBe('avld')
    expect(category('Intercity')).toBe('avld')
    expect(category('LD')).toBe('avld')
    expect(category('MD')).toBe('md')
    expect(category('REG.EXP.')).toBe('md')
    expect(category('AVANT')).toBe('md')
    expect(category('CERCANIAS')).toBe('cer')
  })
})

describe('trainColor', () => {
  it('usa color por categoría en larga y media distancia', () => {
    expect(trainColor({ servicio: 'AVE', color: '#F2F5F5' })).toBe('#E0457B')
    expect(trainColor({ servicio: 'MD', color: '#F2F5F5' })).toBe('#F5A623')
  })
  it('usa el color de la línea en Cercanías, salvo el gris por defecto', () => {
    expect(trainColor({ servicio: 'CERCANIAS', color: '#75B6E0' })).toBe('#75B6E0')
    expect(trainColor({ servicio: 'CERCANIAS', color: '#9AA0A6' })).toBe('#4FC3F7')
    expect(trainColor({ servicio: 'CERCANIAS', color: 'rojo' })).toBe('#4FC3F7')
  })
})

describe('retraso', () => {
  it('nivel', () => {
    expect(delayLevel(null)).toBe('none')
    expect(delayLevel(-3)).toBe('ok')
    expect(delayLevel(4)).toBe('ok')
    expect(delayLevel(5)).toBe('warn')
    expect(delayLevel(14)).toBe('warn')
    expect(delayLevel(15)).toBe('bad')
  })
  it('texto', () => {
    expect(delayLabel(null)).toBe('Sin datos')
    expect(delayLabel(0)).toBe('En hora')
    expect(delayLabel(-3)).toBe('En hora')
    expect(delayLabel(7)).toBe('+7 min')
  })
})

describe('trainTitle', () => {
  it('compone el título', () => {
    expect(trainTitle({ servicio: 'AVE', numero: '03304', linea: null })).toBe('AVE 03304')
    expect(trainTitle({ servicio: 'CERCANIAS', numero: '35903', linea: 'C5' })).toBe('Cercanías C5 · 35903')
    expect(trainTitle({ servicio: 'CERCANIAS', numero: '35903', linea: null })).toBe('Cercanías · 35903')
  })
})

describe('agoLabel', () => {
  it('segundos, minutos y horas', () => {
    expect(agoLabel(5)).toBe('hace 5 s')
    expect(agoLabel(125)).toBe('hace 2 min')
    expect(agoLabel(7300)).toBe('hace 2 h')
  })
})

describe('freshness', () => {
  const ok = { LD: { edad_s: 4, stale: false }, CER: { edad_s: 13, stale: false } }
  it('datos al día', () => {
    expect(freshness(ok, 10_000, 14_000, true)).toEqual({ label: 'hace 4 s', level: 'ok' })
  })
  it('antes de la primera lectura', () => {
    expect(freshness({}, null, 0, true)).toEqual({ label: 'Cargando…', level: 'ok' })
    expect(freshness({}, null, 0, false)).toEqual({ label: 'Sin conexión', level: 'warn' })
  })
  it('sin conexión conserva la edad del último dato', () => {
    expect(freshness(ok, 10_000, 130_000, false)).toEqual({ label: 'Sin conexión · datos de hace 2 min', level: 'warn' })
  })
  it('avisa del feed atrasado', () => {
    const late = { ...ok, LD: { edad_s: 3600, stale: false } }
    expect(freshness(late, 10_000, 14_000, true)).toEqual({
      label: 'Larga y Media Distancia: datos de hace 60 min',
      level: 'warn',
    })
    const stale = { ...ok, CER: { edad_s: 20, stale: true } }
    expect(freshness(stale, 10_000, 14_000, true).label).toBe('Cercanías: datos de hace 20 s')
  })
})
```

- [ ] **Step 3: Ejecutar y ver que falla**

Run: `npm test` → FAIL (no se puede resolver `./format`)

- [ ] **Step 4: Implementación** — `src/lib/format.ts`

```ts
import type { Feeds } from '../api/types'

export type Category = 'avld' | 'md' | 'cer'

const MEDIA_DISTANCIA = new Set(['MD', 'REGIONAL', 'REG.EXP.', 'AVANT', 'PROXIMDAD'])

export const CATEGORY_COLOR: Record<Category, string> = {
  avld: '#E0457B',
  md: '#F5A623',
  cer: '#4FC3F7',
}

export const CATEGORY_NAME: Record<Category, string> = {
  avld: 'Alta velocidad y larga distancia',
  md: 'Media distancia y regionales',
  cer: 'Cercanías',
}

const DEFAULT_API_COLOR = '#9AA0A6'

export function category(servicio: string): Category {
  if (servicio === 'CERCANIAS') return 'cer'
  return MEDIA_DISTANCIA.has(servicio.toUpperCase()) ? 'md' : 'avld'
}

/** Color del icono: el de la línea en Cercanías, uno por categoría en el resto. */
export function trainColor(t: { servicio: string; color: string }): string {
  const cat = category(t.servicio)
  const usable = /^#[0-9a-f]{6}$/i.test(t.color) && t.color.toUpperCase() !== DEFAULT_API_COLOR
  return cat === 'cer' && usable ? t.color : CATEGORY_COLOR[cat]
}

export type DelayLevel = 'none' | 'ok' | 'warn' | 'bad'

export function delayLevel(min: number | null): DelayLevel {
  if (min === null) return 'none'
  if (min < 5) return 'ok'
  return min < 15 ? 'warn' : 'bad'
}

export function delayLabel(min: number | null): string {
  if (min === null) return 'Sin datos'
  return min < 1 ? 'En hora' : `+${min} min`
}

export function trainTitle(t: { servicio: string; numero: string; linea: string | null }): string {
  if (t.servicio === 'CERCANIAS') return `Cercanías ${t.linea ? `${t.linea} ` : ''}· ${t.numero}`
  return `${t.servicio} ${t.numero}`
}

export function agoLabel(seconds: number): string {
  if (seconds < 60) return `hace ${seconds} s`
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`
  return `hace ${Math.floor(seconds / 3600)} h`
}

const FEED_NAME: Record<string, string> = { LD: 'Larga y Media Distancia', CER: 'Cercanías' }
const STALE_AFTER_S = 180

export interface Freshness {
  label: string
  level: 'ok' | 'warn'
}

/** Texto de frescura de los datos. checkedAt: ms de la última lectura correcta, o null si no hay. */
export function freshness(feeds: Feeds, checkedAt: number | null, nowMs: number, online: boolean): Freshness {
  if (checkedAt === null) {
    return online ? { label: 'Cargando…', level: 'ok' } : { label: 'Sin conexión', level: 'warn' }
  }
  const ago = agoLabel(Math.max(0, Math.round((nowMs - checkedAt) / 1000)))
  if (!online) return { label: `Sin conexión · datos de ${ago}`, level: 'warn' }
  const late = Object.entries(feeds).find(([, f]) => f.stale || f.edad_s > STALE_AFTER_S)
  if (late) {
    const [key, feed] = late
    return { label: `${FEED_NAME[key] ?? key}: datos de ${agoLabel(feed.edad_s)}`, level: 'warn' }
  }
  return { label: ago, level: 'ok' }
}
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `npm test` → todos en verde. Run: `npm run build` → sin errores.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/types.ts web/src/lib/format.ts web/src/lib/format.test.ts
git commit -m "feat(web): tipos de la API y utilidades de formato"
```

---

### Task 3: Filtros y preferencias

**Files:**
- Create: `web/src/lib/filters.ts`, `web/src/lib/prefs.ts`
- Test: `web/src/lib/filters.test.ts`

- [ ] **Step 1: Test que falla** — `src/lib/filters.test.ts`

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import type { TrainLight } from '../api/types'
import { applyFilters, DEFAULT_FILTERS, loadFilters, saveFilters } from './filters'
import { loadPrefs, savePrefs } from './prefs'

function train(servicio: string, retraso_min: number | null): TrainLight {
  return { id: servicio + retraso_min, numero: '1', servicio, linea: null, color: '#000000', lat: 0, lon: 0,
           rumbo: null, retraso_min, estado: 'IN_TRANSIT_TO' }
}

const TRAINS = [train('AVE', 0), train('MD', 12), train('CERCANIAS', 3), train('CERCANIAS', null)]

describe('applyFilters', () => {
  it('por defecto muestra todo', () => {
    expect(applyFilters(TRAINS, DEFAULT_FILTERS)).toHaveLength(4)
  })
  it('oculta categorías', () => {
    const out = applyFilters(TRAINS, { ...DEFAULT_FILTERS, cer: false })
    expect(out.map((t) => t.servicio)).toEqual(['AVE', 'MD'])
  })
  it('solo con retraso de 5 min o más', () => {
    const out = applyFilters(TRAINS, { ...DEFAULT_FILTERS, soloRetraso: true })
    expect(out.map((t) => t.servicio)).toEqual(['MD'])
  })
})

describe('persistencia', () => {
  beforeEach(() => localStorage.clear())
  it('filtros: valores por defecto, guardado y datos corruptos', () => {
    expect(loadFilters()).toEqual(DEFAULT_FILTERS)
    saveFilters({ ...DEFAULT_FILTERS, md: false })
    expect(loadFilters().md).toBe(false)
    localStorage.setItem('tr24.filters', '{no es json')
    expect(loadFilters()).toEqual(DEFAULT_FILTERS)
  })
  it('preferencias: tema oscuro por defecto', () => {
    expect(loadPrefs()).toEqual({ theme: 'dark', rails: false })
    savePrefs({ theme: 'light', rails: true })
    expect(loadPrefs()).toEqual({ theme: 'light', rails: true })
  })
})
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `npm test` → FAIL (no se puede resolver `./filters`)

- [ ] **Step 3: Implementación**

`src/lib/filters.ts`:
```ts
import type { TrainLight } from '../api/types'
import { category } from './format'

export interface Filters {
  avld: boolean
  md: boolean
  cer: boolean
  soloRetraso: boolean
}

export const DEFAULT_FILTERS: Filters = { avld: true, md: true, cer: true, soloRetraso: false }
const KEY = 'tr24.filters'
const MIN_DELAY = 5

export function applyFilters(trains: TrainLight[], f: Filters): TrainLight[] {
  return trains.filter((t) => f[category(t.servicio)] && (!f.soloRetraso || (t.retraso_min ?? 0) >= MIN_DELAY))
}

export function loadFilters(): Filters {
  try {
    return { ...DEFAULT_FILTERS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch {
    return DEFAULT_FILTERS
  }
}

export function saveFilters(f: Filters): void {
  localStorage.setItem(KEY, JSON.stringify(f))
}
```

`src/lib/prefs.ts`:
```ts
export type Theme = 'dark' | 'light'

export interface Prefs {
  theme: Theme
  rails: boolean
}

const DEFAULT_PREFS: Prefs = { theme: 'dark', rails: false }
const KEY = 'tr24.prefs'

export function loadPrefs(): Prefs {
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch {
    return DEFAULT_PREFS
  }
}

export function savePrefs(p: Prefs): void {
  localStorage.setItem(KEY, JSON.stringify(p))
}
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `npm test` → en verde. Run: `npm run build` → sin errores.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/filters.ts web/src/lib/prefs.ts web/src/lib/filters.test.ts
git commit -m "feat(web): filtros por categoría y retraso, y preferencias de tema y vías"
```

---

### Task 4: Geometría (`geo.ts`)

**Files:**
- Create: `web/src/lib/geo.ts`
- Test: `web/src/lib/geo.test.ts`

- [ ] **Step 1: Test que falla** — `src/lib/geo.test.ts`

```ts
import { describe, expect, it } from 'vitest'
import type { LngLat } from '../api/types'
import { bounds, interpolate, splitRoute } from './geo'

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
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `npm test` → FAIL (no se puede resolver `./geo`)

- [ ] **Step 3: Implementación** — `src/lib/geo.ts`

```ts
import type { LngLat } from '../api/types'

const MAX_ANIMATED_JUMP_DEG = 0.5

interface Positioned {
  id: string
  lon: number
  lat: number
}

/** Posiciones a mostrar en el instante t (0..1) de la animación entre dos lecturas. */
export function interpolate(prev: Map<string, LngLat>, next: Positioned[], t: number): Map<string, LngLat> {
  const out = new Map<string, LngLat>()
  for (const train of next) {
    const from = prev.get(train.id)
    const jump = from ? Math.max(Math.abs(train.lon - from[0]), Math.abs(train.lat - from[1])) : 0
    if (!from || t >= 1 || jump > MAX_ANIMATED_JUMP_DEG) {
      out.set(train.id, [train.lon, train.lat])
    } else {
      out.set(train.id, [from[0] + (train.lon - from[0]) * t, from[1] + (train.lat - from[1]) * t])
    }
  }
  return out
}

/** Distancia al cuadrado de p al segmento a-b, en grados corregidos por la latitud. */
function segmentDistance2(p: LngLat, a: LngLat, b: LngLat): number {
  const k = Math.cos((p[1] * Math.PI) / 180)
  const ax = (a[0] - p[0]) * k
  const ay = a[1] - p[1]
  const dx = (b[0] - a[0]) * k
  const dy = b[1] - a[1]
  const len2 = dx * dx + dy * dy
  const t = len2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0
  const x = ax + t * dx
  const y = ay + t * dy
  return x * x + y * y
}

/** Parte el trazado en lo ya recorrido y lo pendiente, cortando en el tramo más cercano a p. */
export function splitRoute(shape: LngLat[], p: LngLat): { done: LngLat[]; pending: LngLat[] } {
  if (shape.length < 2) return { done: [], pending: shape }
  let best = 0
  let bestDist = Infinity
  for (let i = 0; i < shape.length - 1; i++) {
    const d = segmentDistance2(p, shape[i], shape[i + 1])
    if (d < bestDist) {
      bestDist = d
      best = i
    }
  }
  return { done: [...shape.slice(0, best + 1), p], pending: [p, ...shape.slice(best + 1)] }
}

/** [[oeste, sur], [este, norte]] o null si no hay puntos. */
export function bounds(points: LngLat[]): [LngLat, LngLat] | null {
  if (!points.length) return null
  const lons = points.map((p) => p[0])
  const lats = points.map((p) => p[1])
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ]
}
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `npm test` → en verde. Run: `npm run build` → sin errores.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/geo.ts web/src/lib/geo.test.ts
git commit -m "feat(web): interpolación de posiciones y corte del trazado recorrido"
```

---

### Task 5: Rutas de la aplicación (`/t/<id>`, `/s/<id>`)

**Files:**
- Create: `web/src/lib/route.ts`, `web/src/hooks/useRoute.ts`
- Test: `web/src/lib/route.test.ts`

- [ ] **Step 1: Test que falla** — `src/lib/route.test.ts`

```ts
import { describe, expect, it } from 'vitest'
import { buildPath, parsePath } from './route'

describe('parsePath', () => {
  it('mapa', () => {
    expect(parsePath('/')).toEqual({ kind: 'map' })
    expect(parsePath('/cualquier/otra')).toEqual({ kind: 'map' })
    expect(parsePath('/t/')).toEqual({ kind: 'map' })
  })
  it('tren, con o sin codificar los dos puntos', () => {
    expect(parsePath('/t/LD:03304')).toEqual({ kind: 'train', id: 'LD:03304' })
    expect(parsePath('/t/LD%3A03304')).toEqual({ kind: 'train', id: 'LD:03304' })
  })
  it('estación', () => {
    expect(parsePath('/s/60000')).toEqual({ kind: 'station', id: '60000' })
  })
})

describe('buildPath', () => {
  it('es la inversa de parsePath', () => {
    expect(buildPath({ kind: 'map' })).toBe('/')
    expect(buildPath({ kind: 'train', id: 'LD:03304' })).toBe('/t/LD:03304')
    expect(buildPath({ kind: 'station', id: '60000' })).toBe('/s/60000')
    expect(parsePath(buildPath({ kind: 'train', id: 'CER:35903' }))).toEqual({ kind: 'train', id: 'CER:35903' })
  })
})
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `npm test` → FAIL (no se puede resolver `./route`)

- [ ] **Step 3: Implementación**

`src/lib/route.ts`:
```ts
export type Route = { kind: 'map' } | { kind: 'train'; id: string } | { kind: 'station'; id: string }

export function parsePath(path: string): Route {
  const m = /^\/([ts])\/(.+)$/.exec(path)
  if (!m) return { kind: 'map' }
  const id = decodeURIComponent(m[2])
  return m[1] === 't' ? { kind: 'train', id } : { kind: 'station', id }
}

export function buildPath(route: Route): string {
  if (route.kind === 'map') return '/'
  const id = encodeURIComponent(route.id).replace(/%3A/g, ':')
  return `/${route.kind === 'train' ? 't' : 's'}/${id}`
}
```

`src/hooks/useRoute.ts`:
```ts
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
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `npm test` → en verde. Run: `npm run build` → sin errores.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/route.ts web/src/lib/route.test.ts web/src/hooks/useRoute.ts
git commit -m "feat(web): rutas enlazables para tren y estación"
```

---

### Task 6: Cliente de la API

**Files:**
- Create: `web/src/api/client.ts`
- Test: `web/src/api/client.test.ts`

- [ ] **Step 1: Test que falla** — `src/api/client.test.ts`

```ts
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
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `npm test` → FAIL (no se puede resolver `./client`)

- [ ] **Step 3: Implementación** — `src/api/client.ts`

```ts
import type { Avisos, BoardKind, BoardResponse, Favorite, FavoriteKind, SearchResponse, Station, TrainDetail,
              TrainsResponse } from './types'

const DEVICE_KEY = 'tr24.device'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function randomId(): string {
  // crypto.randomUUID solo existe en contexto seguro (HTTPS o localhost).
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return Array.from({ length: 4 }, () => Math.random().toString(36).slice(2, 10)).join('')
}

/** Identificador anónimo de este navegador; con él se guardan favoritos y avisos. */
export function deviceId(): string {
  let id = localStorage.getItem(DEVICE_KEY)
  if (!id) {
    id = randomId()
    localStorage.setItem(DEVICE_KEY, id)
  }
  return id
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) throw new ApiError(res.status, `${res.status} en ${path}`)
  return (await res.json()) as T
}

function asDevice(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'X-Device-Id': deviceId(), 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }
}

export interface TrainsResult {
  data: TrainsResponse | null // null: el servidor respondió 304, nada ha cambiado
  etag: string | null
}

export async function getTrains(etag: string | null): Promise<TrainsResult> {
  const res = await fetch('/api/trains', { headers: etag ? { 'If-None-Match': etag } : {} })
  if (res.status === 304) return { data: null, etag }
  if (!res.ok) throw new ApiError(res.status, `${res.status} en /trains`)
  return { data: (await res.json()) as TrainsResponse, etag: res.headers.get('ETag') }
}

export const getTrain = (id: string) => request<TrainDetail>(`/trains/${encodeURIComponent(id)}`)

export const search = (q: string) => request<SearchResponse>(`/search?q=${encodeURIComponent(q)}`)

export const stationsNear = (lat: number, lon: number) => request<Station[]>(`/stations/near?lat=${lat}&lon=${lon}`)

export const getBoard = (stationId: string, tipo: BoardKind) =>
  request<BoardResponse>(`/stations/${encodeURIComponent(stationId)}/board?tipo=${tipo}`)

export const listFavorites = () => request<Favorite[]>('/favorites', asDevice('GET'))

export const putFavorite = (fav: { tipo: FavoriteKind; ref: string; avisos?: Avisos }) =>
  request<{ ok: boolean }>('/favorites', asDevice('PUT', fav))

export const deleteFavorite = (tipo: FavoriteKind, ref: string) =>
  request<{ ok: boolean }>(`/favorites?tipo=${tipo}&ref=${encodeURIComponent(ref)}`, asDevice('DELETE'))

export const getVapidKey = () => request<{ key: string }>('/push/vapid-public-key')

export const saveSubscription = (sub: { endpoint: string; keys: Record<string, string> }) =>
  request<{ ok: boolean }>('/push/subscription', asDevice('POST', sub))

export const deleteSubscription = () => request<{ ok: boolean }>('/push/subscription', asDevice('DELETE'))
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `npm test` → en verde. Run: `npm run build` → sin errores.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/client.ts web/src/api/client.test.ts
git commit -m "feat(web): cliente de la API con ETag e id de dispositivo"
```

---

### Task 7: Hooks de datos

No llevan pruebas propias: son envoltorios finos sobre el cliente (ya probado) y se verifican en la tarea 12 con la app en marcha.

**Files:**
- Create: `web/src/hooks/useNow.ts`, `web/src/hooks/useTrains.ts`, `web/src/hooks/useTrainDetail.ts`, `web/src/hooks/useFavorites.ts`

- [ ] **Step 1: `src/hooks/useNow.ts`**

```ts
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
```

- [ ] **Step 2: `src/hooks/useTrains.ts`**

```ts
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
```

- [ ] **Step 3: `src/hooks/useTrainDetail.ts`**

```ts
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
```

- [ ] **Step 4: `src/hooks/useFavorites.ts`**

```ts
import { useCallback, useEffect, useState } from 'react'
import { deleteFavorite, listFavorites, putFavorite } from '../api/client'
import type { Avisos, Favorite, FavoriteKind } from '../api/types'

/** Favoritos de este dispositivo. Tras cada cambio se relee la lista del servidor. */
export function useFavorites() {
  const [list, setList] = useState<Favorite[]>([])

  const reload = useCallback(async () => {
    try {
      setList(await listFavorites())
    } catch {
      // Sin conexión: se conserva la lista que hubiera.
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const has = useCallback(
    (tipo: FavoriteKind, ref: string) => list.some((f) => f.tipo === tipo && f.ref === ref),
    [list],
  )

  const toggle = useCallback(
    async (tipo: FavoriteKind, ref: string) => {
      try {
        if (has(tipo, ref)) await deleteFavorite(tipo, ref)
        else await putFavorite({ tipo, ref })
      } finally {
        await reload()
      }
    },
    [has, reload],
  )

  const setAvisos = useCallback(
    async (fav: Favorite, avisos: Avisos) => {
      try {
        await putFavorite({ tipo: fav.tipo, ref: fav.ref, avisos })
      } finally {
        await reload()
      }
    },
    [reload],
  )

  return { list, has, toggle, setAvisos }
}
```

- [ ] **Step 5: Verificar**

Run: `npm test` → en verde. Run: `npm run build` → sin errores de tipos.

- [ ] **Step 6: Commit**

```bash
git add web/src/hooks
git commit -m "feat(web): hooks de sondeo de trenes, ficha y favoritos"
```

---

### Task 8: Mapa (`MapView`)

**Files:**
- Create: `web/src/components/MapView.tsx`

- [ ] **Step 1: Implementación** — `src/components/MapView.tsx`

```tsx
import maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MlMap, RasterTileSource, StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import type { LngLat, TrainDetail, TrainLight } from '../api/types'
import { trainColor } from '../lib/format'
import { bounds, interpolate, splitRoute } from '../lib/geo'
import type { Theme } from '../lib/prefs'

const ANIM_MS = 14_000 // casi lo que tarda en llegar la siguiente lectura (15 s)
const FRAME_MS = 100
const SPAIN_CENTER: LngLat = [-3.7, 40.2]
const ATTRIBUTION = 'Datos: Renfe (CC BY 4.0) · © OpenStreetMap · © CARTO'

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
  onSelect(id: string | null): void
}

function baseTiles(theme: Theme): string[] {
  const variant = theme === 'dark' ? 'dark_all' : 'light_all'
  return ['a', 'b', 'c', 'd'].map((s) => `https://${s}.basemaps.cartocdn.com/${variant}/{z}/{x}/{y}.png`)
}

function baseStyle(theme: Theme): StyleSpecification {
  return {
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
      base: { type: 'raster', tiles: baseTiles(theme), tileSize: 256, attribution: ATTRIBUTION },
      rails: {
        type: 'raster',
        tiles: ['a', 'b', 'c'].map((s) => `https://${s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png`),
        tileSize: 256,
        attribution: '© OpenRailwayMap',
      },
    },
    layers: [
      { id: 'base', type: 'raster', source: 'base' },
      { id: 'rails', type: 'raster', source: 'rails', paint: { 'raster-opacity': 0.55 }, layout: { visibility: 'none' } },
    ],
  }
}

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

function line(coords: LngLat[]): GeoJSON.FeatureCollection {
  if (coords.length < 2) return EMPTY
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } }] }
}

function addLayers(map: MlMap, theme: Theme): void {
  for (const id of ['route-done', 'route-pending', 'route-stops', 'selected', 'trains']) {
    map.addSource(id, { type: 'geojson', data: EMPTY })
  }
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
      'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.5, 10, 0.85, 14, 1.15],
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

/** Dibuja un icono de tren (flecha si hay rumbo, punto si no) y lo registra en el mapa. */
function ensureIcon(map: MlMap, color: string, arrow: boolean): string {
  const name = `${arrow ? 'arrow' : 'dot'}-${color}`
  if (map.hasImage(name)) return name
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const g = canvas.getContext('2d')
  if (!g) return name
  g.lineJoin = 'round'
  g.lineWidth = 6
  g.strokeStyle = '#ffffff'
  g.fillStyle = color
  g.beginPath()
  if (arrow) {
    g.moveTo(32, 6)
    g.lineTo(52, 56)
    g.lineTo(32, 45)
    g.lineTo(12, 56)
    g.closePath()
  } else {
    g.arc(32, 32, 15, 0, Math.PI * 2)
  }
  g.stroke()
  g.fill()
  map.addImage(name, g.getImageData(0, 0, size, size), { pixelRatio: 2 })
  return name
}

function setData(map: MlMap, source: string, data: GeoJSON.FeatureCollection): void {
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
    const features: GeoJSON.Feature[] = []
    for (const t of trains) {
      const pos = shown.current.get(t.id)
      if (!pos) continue
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: pos },
        properties: { id: t.id, label: t.numero, rumbo: t.rumbo ?? 0, icon: ensureIcon(map, trainColor(t), t.rumbo !== null) },
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
    const map = new maplibregl.Map({
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

  // Tema: cambiar las teselas del mapa base y el color de las etiquetas.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    (map.getSource('base') as RasterTileSource | undefined)?.setTiles(baseTiles(props.theme))
    map.setPaintProperty('trains', 'text-color', props.theme === 'dark' ? '#e8eaed' : '#202124')
    map.setPaintProperty('trains', 'text-halo-color', props.theme === 'dark' ? '#10151c' : '#ffffff')
  }, [props.theme, ready])

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
```

- [ ] **Step 2: Verificar**

Run: `npm run build`
Expected: sin errores de tipos. Si TypeScript rechaza alguna expresión de estilo de MapLibre por la versión instalada, ajustar el tipo con el cambio mínimo (por ejemplo, anotar la expresión como `maplibregl.ExpressionSpecification`), sin cambiar el comportamiento.

Run: `npm test` → en verde.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/MapView.tsx
git commit -m "feat(web): mapa con capa de trenes animada, selección y recorrido"
```

---

### Task 9: Ficha del tren (`TrainSheet`)

**Files:**
- Create: `web/src/components/TrainSheet.tsx`

- [ ] **Step 1: Implementación** — `src/components/TrainSheet.tsx`

```tsx
import { useState } from 'react'
import type { TrainDetail } from '../api/types'
import { delayLabel, delayLevel, trainTitle } from '../lib/format'
import { buildPath } from '../lib/route'

interface Props {
  detail: TrainDetail | null
  gone: boolean
  favorite: boolean
  following: boolean
  onClose(): void
  onFavorite(numero: string): void
  onFollow(): void
  onRoute(): void
  onStation(id: string): void
}

async function share(d: TrainDetail): Promise<void> {
  const trayecto = d.origen && d.destino ? ` ${d.origen} → ${d.destino}` : ''
  const text = `${trainTitle(d)}${trayecto} · ${delayLabel(d.retraso_min)}`
  const url = location.origin + buildPath({ kind: 'train', id: d.id })
  try {
    if (navigator.share) await navigator.share({ title: trainTitle(d), text, url })
    else await navigator.clipboard.writeText(`${text} ${url}`)
  } catch {
    // El usuario canceló o el navegador no lo permite: no hay nada que hacer.
  }
}

export function TrainSheet({ detail, gone, favorite, following, onClose, onFavorite, onFollow, onRoute, onStation }: Props) {
  const [expanded, setExpanded] = useState(false)

  if (gone) {
    return (
      <section className="sheet">
        <div className="sheet-head">
          <strong>Este tren ya no está en circulación</strong>
          <button className="icon-btn" onClick={onClose} aria-label="Cerrar">✕</button>
        </div>
      </section>
    )
  }
  if (!detail) {
    return (
      <section className="sheet">
        <p className="muted">Cargando…</p>
      </section>
    )
  }

  const suprimidas = detail.paradas.filter((p) => p.estado === 'suprimida')
  const next = detail.proxima_parada

  return (
    <section className={`sheet ${expanded ? 'expanded' : ''}`}>
      <div className="sheet-head">
        <div>
          <strong className="train-title">{trainTitle(detail)}</strong>
          <span className={`chip delay-${delayLevel(detail.retraso_min)}`}>{delayLabel(detail.retraso_min)}</span>
          {detail.anden && <span className="chip">Andén {detail.anden}</span>}
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Cerrar">✕</button>
      </div>

      {detail.origen && detail.destino ? (
        <>
          <div className="trip">
            <span>{detail.origen}</span>
            <span className="arrow">→</span>
            <span>{detail.destino}</span>
          </div>
          <div className="progress" role="progressbar" aria-valuenow={Math.round((detail.progreso ?? 0) * 100)}
               aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${Math.round((detail.progreso ?? 0) * 100)}%` }} />
          </div>
        </>
      ) : (
        <p className="muted">Renfe no publica el recorrido de este tren.</p>
      )}

      {next && (
        <p className="next">
          Próxima parada:{' '}
          <button className="link" onClick={() => onStation(next.id)}>{next.nombre}</button>{' '}
          a las <strong>{next.hora_est}</strong>
          {next.hora_est !== next.hora_prog && <span className="muted"> (prevista {next.hora_prog})</span>}
        </p>
      )}

      {detail.cancelado && <p className="notice bad">Renfe marca este tren como cancelado.</p>}
      {!detail.cancelado && suprimidas.length > 0 && (
        <p className="notice warn">Según Renfe, no para en: {suprimidas.map((p) => p.nombre).join(', ')}.</p>
      )}

      <div className="actions">
        <button onClick={() => onFavorite(detail.numero)} aria-pressed={favorite}>{favorite ? '★ Favorito' : '☆ Favorito'}</button>
        <button onClick={onFollow} aria-pressed={following}>{following ? 'Siguiendo' : 'Seguir'}</button>
        <button onClick={onRoute} disabled={detail.shape.length < 2}>Ruta</button>
        <button onClick={() => void share(detail)}>Compartir</button>
        <button onClick={() => setExpanded(!expanded)} disabled={detail.paradas.length === 0}>
          {expanded ? 'Menos' : 'Paradas'}
        </button>
      </div>

      {expanded && (
        <ol className="stops">
          {detail.paradas.map((p) => (
            <li key={p.id + p.ts_prog} className={`stop ${p.estado}`}>
              <span className="time">
                {p.hora_est !== p.hora_prog && <s>{p.hora_prog}</s>} {p.hora_est}
              </span>
              <button className="link" onClick={() => onStation(p.id)}>{p.nombre}</button>
              {p.estado === 'suprimida' && <span className="chip delay-bad">Suprimida</span>}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
```

- [ ] **Step 2: Verificar**

Run: `npm run build` → sin errores. Run: `npm test` → en verde.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/TrainSheet.tsx
git commit -m "feat(web): ficha del tren con progreso, próxima parada, paradas y acciones"
```

---

### Task 10: Búsqueda y panel de estación

**Files:**
- Create: `web/src/components/SearchPanel.tsx`, `web/src/components/StationBoard.tsx`

- [ ] **Step 1: `src/components/SearchPanel.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { search, stationsNear } from '../api/client'
import type { SearchResponse, Station } from '../api/types'
import { delayLabel, delayLevel, trainTitle } from '../lib/format'

interface Props {
  onClose(): void
  onTrain(id: string): void
  onStation(id: string): void
}

const DEBOUNCE_MS = 300
const EMPTY: SearchResponse = { trenes: [], estaciones: [] }

export function SearchPanel({ onClose, onTrain, onStation }: Props) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SearchResponse>(EMPTY)
  const [near, setNear] = useState<Station[] | null>(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    const text = q.trim()
    if (text.length < 2) {
      setResults(EMPTY)
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      search(text)
        .then((r) => { if (!cancelled) { setResults(r); setMessage('') } })
        .catch(() => { if (!cancelled) setMessage('No se pudo buscar. Comprueba la conexión.') })
    }, DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [q])

  const findNear = () => {
    if (!navigator.geolocation) {
      setMessage('Este navegador no permite obtener la ubicación.')
      return
    }
    setMessage('Buscando tu ubicación…')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        stationsNear(pos.coords.latitude, pos.coords.longitude)
          .then((list) => { setNear(list); setMessage('') })
          .catch(() => setMessage('No se pudieron cargar las estaciones cercanas.'))
      },
      () => setMessage('No se pudo obtener la ubicación.'),
    )
  }

  const typed = q.trim().length >= 2
  const nothing = typed && !message && results.trenes.length === 0 && results.estaciones.length === 0

  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} inputMode="search"
               placeholder="Ej.: 03304, Atocha, Sants" aria-label="Buscar tren o estación" />
      </div>
      <div className="panel-body">
        {message && <p className="muted">{message}</p>}
        {!typed && (
          <button className="row" onClick={findNear}>Estaciones cerca de mí</button>
        )}
        {!typed && near?.map((s) => (
          <button key={s.id} className="row" onClick={() => onStation(s.id)}>
            <span>{s.nombre}</span>
            <span className="muted">{s.dist_m !== undefined && (s.dist_m < 1000 ? `${s.dist_m} m` : `${(s.dist_m / 1000).toFixed(1)} km`)}</span>
          </button>
        ))}
        {results.trenes.length > 0 && <h3>Trenes</h3>}
        {results.trenes.map((t) => (
          <button key={t.id} className="row" onClick={() => onTrain(t.id)}>
            <span>{trainTitle(t)}</span>
            <span className={`chip delay-${delayLevel(t.retraso_min)}`}>{delayLabel(t.retraso_min)}</span>
          </button>
        ))}
        {results.estaciones.length > 0 && <h3>Estaciones</h3>}
        {results.estaciones.map((s) => (
          <button key={s.id} className="row" onClick={() => onStation(s.id)}>{s.nombre}</button>
        ))}
        {nothing && <p className="muted">Sin resultados. Los trenes se buscan por número y solo aparecen si están circulando.</p>}
      </div>
    </section>
  )
}
```

- [ ] **Step 2: `src/components/StationBoard.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { ApiError, getBoard } from '../api/client'
import type { BoardKind, BoardResponse, BoardRow } from '../api/types'
import { delayLevel } from '../lib/format'

interface Props {
  stationId: string
  favorite: boolean
  onClose(): void
  onFavorite(): void
  onTrain(id: string): void
}

const POLL_MS = 30_000

function statusText(row: BoardRow): string {
  if (row.estado === 'cancelado') return 'Cancelado'
  if (row.estado === 'suprimida') return 'No para'
  if (row.retraso_min === null) return ''
  return row.retraso_min < 1 ? 'En hora' : `+${row.retraso_min} min`
}

export function StationBoard({ stationId, favorite, onClose, onFavorite, onTrain }: Props) {
  const [tipo, setTipo] = useState<BoardKind>('salidas')
  const [board, setBoard] = useState<BoardResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    setBoard(null)
    setError('')
    const tick = async () => {
      try {
        const next = await getBoard(stationId, tipo)
        if (stopped) return
        setBoard(next)
        setError('')
      } catch (err) {
        if (stopped) return
        setError(err instanceof ApiError && err.status === 404 ? 'Estación no encontrada.' : 'No se pudo cargar el panel.')
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS)
    }
    void tick()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [stationId, tipo])

  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <strong className="grow">{board?.estacion.nombre ?? 'Estación'}</strong>
        <button className="icon-btn" onClick={onFavorite} aria-pressed={favorite} aria-label="Favorita">{favorite ? '★' : '☆'}</button>
      </div>
      <div className="tabs" role="tablist">
        {(['salidas', 'llegadas'] as const).map((k) => (
          <button key={k} role="tab" aria-selected={tipo === k} onClick={() => setTipo(k)}>
            {k === 'salidas' ? 'Salidas' : 'Llegadas'}
          </button>
        ))}
      </div>
      <div className="panel-body">
        {error && <p className="muted">{error}</p>}
        {!error && !board && <p className="muted">Cargando…</p>}
        {board && board.filas.length === 0 && <p className="muted">No hay trenes en las próximas 3 horas.</p>}
        {board?.filas.map((row) => (
          <button key={`${row.numero}-${row.ts_prog}`} className="row board-row" disabled={!row.train_id}
                  onClick={() => row.train_id && onTrain(row.train_id)}>
            <span className="time">
              {row.hora_est !== row.hora_prog && <s>{row.hora_prog}</s>} {row.hora_est}
            </span>
            <span className="grow">
              <span>{tipo === 'salidas' ? row.destino : row.origen}</span>
              <small className="muted">
                {row.linea ?? row.servicio} {row.numero}{row.anden ? ` · Andén ${row.anden}` : ''}
              </small>
            </span>
            <span className={`chip delay-${row.estado === 'cancelado' || row.estado === 'suprimida' ? 'bad' : delayLevel(row.retraso_min)}`}>
              {statusText(row) || 'Programado'}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Verificar**

Run: `npm run build` → sin errores. Run: `npm test` → en verde.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/SearchPanel.tsx web/src/components/StationBoard.tsx
git commit -m "feat(web): búsqueda de trenes y estaciones y panel de salidas y llegadas"
```

---

### Task 11: Avisos push, service worker, manifiesto, filtros y favoritos

**Files:**
- Create: `web/src/lib/push.ts`, `web/public/sw.js`, `web/public/manifest.webmanifest`, `web/scripts/make_icons.py`, `web/public/icon-192.png`, `web/public/icon-512.png`, `web/src/components/FiltersPanel.tsx`, `web/src/components/FavoritesPanel.tsx`
- Test: `web/src/lib/push.test.ts`

- [ ] **Step 1: Test que falla** — `src/lib/push.test.ts`

```ts
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
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `npm test` → FAIL (no se puede resolver `./push`)

- [ ] **Step 3: `src/lib/push.ts`**

```ts
import { deleteSubscription, getVapidKey, saveSubscription } from '../api/client'

export type PushResult = 'ok' | 'denied' | 'unsupported' | 'unconfigured' | 'error'

export function urlBase64ToUint8Array(base64url: string): Uint8Array {
  const padded = base64url + '='.repeat((4 - (base64url.length % 4)) % 4)
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

/** Los avisos necesitan service worker, Push API y contexto seguro (HTTPS o localhost). */
export function pushSupported(): boolean {
  return window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

export async function pushEnabled(): Promise<boolean> {
  if (!pushSupported() || Notification.permission !== 'granted') return false
  const reg = await navigator.serviceWorker.getRegistration()
  return Boolean(reg && (await reg.pushManager.getSubscription()))
}

export async function enablePush(): Promise<PushResult> {
  if (!pushSupported()) return 'unsupported'
  try {
    const { key } = await getVapidKey()
    if (!key) return 'unconfigured'
    if ((await Notification.requestPermission()) !== 'granted') return 'denied'
    const reg = await navigator.serviceWorker.ready
    const sub =
      (await reg.pushManager.getSubscription()) ??
      (await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key).buffer as ArrayBuffer,
      }))
    const json = sub.toJSON()
    if (!json.endpoint || !json.keys) return 'error'
    await saveSubscription({ endpoint: json.endpoint, keys: json.keys })
    return 'ok'
  } catch {
    return 'error'
  }
}

export async function disablePush(): Promise<void> {
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  await sub?.unsubscribe()
  await deleteSubscription().catch(() => undefined)
}
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `npm test` → en verde.

- [ ] **Step 5: Service worker** — `public/sw.js`

```js
// Service worker de TrainRadar24h: guarda la app para abrirla sin conexión y muestra los avisos push.
const CACHE = 'tr24-shell-v1'

self.addEventListener('install', () => self.skipWaiting())

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key)
    await self.clients.claim()
  })())
})

// Red primero; si falla, lo guardado. La API y las teselas del mapa no se guardan.
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return
  event.respondWith((async () => {
    const cache = await caches.open(CACHE)
    try {
      const response = await fetch(event.request)
      if (response.ok) await cache.put(event.request, response.clone())
      return response
    } catch {
      const cached = (await cache.match(event.request)) ||
        (event.request.mode === 'navigate' ? await cache.match('/') : undefined)
      return cached || Response.error()
    }
  })())
})

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = {}
  }
  event.waitUntil(self.registration.showNotification(data.title || 'TrainRadar24h', {
    body: data.body || '',
    tag: data.tag,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    data: { url: data.url || '/' },
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const client of windows) {
      if ('navigate' in client) {
        await client.navigate(url).catch(() => undefined)
        return client.focus()
      }
    }
    return self.clients.openWindow(url)
  })())
})
```

- [ ] **Step 6: Manifiesto** — `public/manifest.webmanifest`

```json
{
  "name": "TrainRadar24h",
  "short_name": "TrainRadar",
  "description": "Trenes de Renfe en tiempo real sobre el mapa",
  "lang": "es",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#10151c",
  "theme_color": "#10151c",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ]
}
```

- [ ] **Step 7: Iconos** — `scripts/make_icons.py`

```python
"""Genera los iconos PNG de la PWA. Uso: python scripts/make_icons.py (desde web/). Requiere Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "public"
BACKGROUND = (16, 21, 28, 255)
ARROW = (224, 69, 123, 255)


def make(size: int) -> None:
    img = Image.new("RGBA", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(img)
    s = size / 64  # el dibujo está pensado en una rejilla de 64 con margen para máscaras
    points = [(32, 14), (46, 50), (32, 42), (18, 50)]
    draw.polygon([(x * s, y * s) for x, y in points], fill=ARROW, outline=(255, 255, 255, 255), width=max(1, round(2 * s)))
    img.save(OUT / f"icon-{size}.png")


for px in (192, 512):
    make(px)
print("Iconos generados en", OUT)
```

Run (desde `web/`): `python scripts/make_icons.py`
Expected: crea `public/icon-192.png` y `public/icon-512.png`. Si el `python` del sistema no tiene Pillow, instalarlo solo para este paso con `python -m pip install --user pillow`.

- [ ] **Step 8: `src/components/FiltersPanel.tsx`**

```tsx
import type { Filters } from '../lib/filters'
import type { Category } from '../lib/format'
import { CATEGORY_COLOR, CATEGORY_NAME } from '../lib/format'
import type { Prefs } from '../lib/prefs'

interface Props {
  filters: Filters
  prefs: Prefs
  counts: Record<Category, number>
  onFilters(next: Filters): void
  onPrefs(next: Prefs): void
  onClose(): void
}

const CATEGORIES: Category[] = ['avld', 'md', 'cer']

export function FiltersPanel({ filters, prefs, counts, onFilters, onPrefs, onClose }: Props) {
  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <strong className="grow">Filtros y mapa</strong>
      </div>
      <div className="panel-body">
        <h3>Trenes</h3>
        {CATEGORIES.map((cat) => (
          <label key={cat} className="row">
            <span><i className="swatch" style={{ background: CATEGORY_COLOR[cat] }} /> {CATEGORY_NAME[cat]} <small className="muted">({counts[cat]})</small></span>
            <input type="checkbox" checked={filters[cat]} onChange={(e) => onFilters({ ...filters, [cat]: e.target.checked })} />
          </label>
        ))}
        <label className="row">
          <span>Solo con retraso de 5 min o más</span>
          <input type="checkbox" checked={filters.soloRetraso} onChange={(e) => onFilters({ ...filters, soloRetraso: e.target.checked })} />
        </label>
        <h3>Mapa</h3>
        <label className="row">
          <span>Tema claro</span>
          <input type="checkbox" checked={prefs.theme === 'light'} onChange={(e) => onPrefs({ ...prefs, theme: e.target.checked ? 'light' : 'dark' })} />
        </label>
        <label className="row">
          <span>Mostrar vías (OpenRailwayMap)</span>
          <input type="checkbox" checked={prefs.rails} onChange={(e) => onPrefs({ ...prefs, rails: e.target.checked })} />
        </label>
        <p className="muted small">Datos: Renfe (CC BY 4.0). Mapa: © OpenStreetMap, © CARTO, © OpenRailwayMap.</p>
      </div>
    </section>
  )
}
```

- [ ] **Step 9: `src/components/FavoritesPanel.tsx`**

```tsx
import { useEffect, useState } from 'react'
import type { Avisos, Favorite, FavoriteKind, TrainLight } from '../api/types'
import { delayLabel, delayLevel, trainTitle } from '../lib/format'
import type { PushResult } from '../lib/push'
import { disablePush, enablePush, pushEnabled, pushSupported } from '../lib/push'

interface Props {
  favorites: Favorite[]
  trains: TrainLight[]
  onAvisos(fav: Favorite, avisos: Avisos): void
  onRemove(tipo: FavoriteKind, ref: string): void
  onTrain(id: string): void
  onStation(id: string): void
  onClose(): void
}

const AVISO_LABEL: Record<keyof Avisos, string> = {
  retraso: 'Retraso',
  cancelacion: 'Cancelación',
  anden: 'Cambio de andén',
  salida: 'Sale en 15 min',
}

const PUSH_MESSAGE: Record<PushResult, string> = {
  ok: 'Avisos activados en este dispositivo.',
  denied: 'El navegador ha bloqueado las notificaciones para esta página.',
  unsupported: 'Este navegador no admite avisos, o la página no está en HTTPS.',
  unconfigured: 'El servidor no tiene configurados los avisos push.',
  error: 'No se pudieron activar los avisos.',
}

export function FavoritesPanel({ favorites, trains, onAvisos, onRemove, onTrain, onStation, onClose }: Props) {
  const [enabled, setEnabled] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    void pushEnabled().then(setEnabled)
  }, [])

  const togglePush = async () => {
    if (enabled) {
      await disablePush()
      setEnabled(false)
      setMessage('Avisos desactivados en este dispositivo.')
      return
    }
    const result = await enablePush()
    setEnabled(result === 'ok')
    setMessage(PUSH_MESSAGE[result])
  }

  const trenes = favorites.filter((f) => f.tipo === 'tren')
  const estaciones = favorites.filter((f) => f.tipo === 'estacion')

  return (
    <section className="panel">
      <div className="panel-head">
        <button className="icon-btn" onClick={onClose} aria-label="Volver">←</button>
        <strong className="grow">Favoritos</strong>
      </div>
      <div className="panel-body">
        <div className="row">
          <span>Avisos en este dispositivo</span>
          <button onClick={() => void togglePush()} disabled={!pushSupported()} aria-pressed={enabled}>
            {enabled ? 'Desactivar' : 'Activar'}
          </button>
        </div>
        {!pushSupported() && <p className="muted small">Los avisos necesitan HTTPS (o localhost) y un navegador compatible.</p>}
        {message && <p className="muted small">{message}</p>}

        <h3>Trenes</h3>
        {trenes.length === 0 && <p className="muted">Abre un tren y pulsa «Favorito» para seguirlo.</p>}
        {trenes.map((fav) => {
          const live = trains.find((t) => t.numero === fav.ref)
          return (
            <div key={fav.ref} className="fav">
              <div className="row">
                <button className="link grow" disabled={!live} onClick={() => live && onTrain(live.id)}>
                  {live ? trainTitle(live) : `Tren ${fav.ref}`}
                </button>
                {live
                  ? <span className={`chip delay-${delayLevel(live.retraso_min)}`}>{delayLabel(live.retraso_min)}</span>
                  : <span className="muted small">No circula ahora</span>}
                <button className="icon-btn" onClick={() => onRemove('tren', fav.ref)} aria-label="Quitar favorito">✕</button>
              </div>
              <div className="avisos">
                {(Object.keys(AVISO_LABEL) as (keyof Avisos)[]).map((key) => (
                  <label key={key}>
                    <input type="checkbox" checked={fav.avisos[key]}
                           onChange={(e) => onAvisos(fav, { ...fav.avisos, [key]: e.target.checked })} />
                    {AVISO_LABEL[key]}
                  </label>
                ))}
              </div>
            </div>
          )
        })}

        <h3>Estaciones</h3>
        {estaciones.length === 0 && <p className="muted">Abre una estación y pulsa la estrella para guardarla.</p>}
        {estaciones.map((fav) => (
          <div key={fav.ref} className="row">
            <button className="link grow" onClick={() => onStation(fav.ref)}>Estación {fav.ref}</button>
            <button className="icon-btn" onClick={() => onRemove('estacion', fav.ref)} aria-label="Quitar favorita">✕</button>
          </div>
        ))}
      </div>
    </section>
  )
}
```

Nota: la API guarda de la estación favorita solo su código, así que aquí se muestra «Estación 60000». El nombre aparece al abrir su panel. Mostrar el nombre en la lista queda fuera de este plan.

- [ ] **Step 10: Verificar**

Run: `npm test` → en verde. Run: `npm run build` → sin errores, y `dist/` contiene `sw.js`, `manifest.webmanifest` y los dos iconos.

- [ ] **Step 11: Commit**

```bash
git add web/src/lib/push.ts web/src/lib/push.test.ts web/public web/scripts web/src/components/FiltersPanel.tsx web/src/components/FavoritesPanel.tsx
git commit -m "feat(web): avisos push, service worker, manifiesto, filtros y favoritos"
```

---

### Task 12: Composición de la app (`App.tsx`) y estilos

**Files:**
- Modify: `web/src/App.tsx` (sustituir entero), `web/src/main.tsx`, `web/src/styles.css` (sustituir entero)

- [ ] **Step 1: `src/App.tsx`**

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { TrainLight } from './api/types'
import { FavoritesPanel } from './components/FavoritesPanel'
import { FiltersPanel } from './components/FiltersPanel'
import type { MapHandle } from './components/MapView'
import { MapView } from './components/MapView'
import { SearchPanel } from './components/SearchPanel'
import { StationBoard } from './components/StationBoard'
import { TrainSheet } from './components/TrainSheet'
import { useFavorites } from './hooks/useFavorites'
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

type Panel = 'search' | 'filters' | 'favorites' | null

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
    const out: Record<Category, number> = { avld: 0, md: 0, cer: 0 }
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

  const locate = () => {
    if (!navigator.geolocation) {
      setToast('Este navegador no permite obtener la ubicación.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => mapRef.current?.flyTo([pos.coords.longitude, pos.coords.latitude], 11),
      () => setToast('No se pudo obtener la ubicación.'),
    )
  }

  const fresh = freshness(resp?.feeds ?? {}, checkedAt, now, online)
  const filtersActive = !filters.avld || !filters.md || !filters.cer || filters.soloRetraso

  return (
    <div className="app">
      <MapView ref={mapRef} trains={visible} selectedId={selectedId} detail={detail} follow={follow}
               theme={prefs.theme} rails={prefs.rails} onSelect={selectTrain} />

      <header className="topbar">
        <button className="searchbox" onClick={() => setPanel('search')}>Buscar tren o estación</button>
        <span className={`fresh ${fresh.level}`} role="status">{fresh.label}</span>
      </header>

      {!selectedId && (
        <nav className="bottombar">
          <button onClick={() => setPanel('filters')}>Filtros{filtersActive ? ' •' : ''}</button>
          <button onClick={() => setPanel('favorites')}>Favoritos</button>
          <button onClick={locate}>Mi ubicación</button>
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

      {toast && <div className="toast" role="alert">{toast}</div>}
    </div>
  )
}
```

- [ ] **Step 2: Registrar el service worker** — sustituir `src/main.tsx` por:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// Solo en la versión de producción: en desarrollo el service worker interfiere con la recarga en caliente.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined)
  })
}
```

- [ ] **Step 3: Estilos** — sustituir `src/styles.css` por:

```css
:root {
  --bg: #10151c;
  --surface: #1a212b;
  --surface-2: #232c38;
  --text: #e8eaed;
  --muted: #9aa0a6;
  --accent: #8ab4f8;
  --ok: #81c995;
  --warn: #fdd663;
  --bad: #f28b82;
  --border: #2d3743;
  color-scheme: dark;
}
:root[data-theme='light'] {
  --bg: #f1f3f4;
  --surface: #ffffff;
  --surface-2: #f1f3f4;
  --text: #202124;
  --muted: #5f6368;
  --accent: #1a73e8;
  --ok: #188038;
  --warn: #b06000;
  --bad: #c5221f;
  --border: #dadce0;
  color-scheme: light;
}

* { box-sizing: border-box; }
html, body, #root { height: 100%; margin: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font: 15px/1.4 system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  overscroll-behavior: none;
}
button, input { font: inherit; color: inherit; }
button { cursor: pointer; background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; padding: 8px 12px; }
button:disabled { opacity: 0.5; cursor: default; }
button[aria-pressed='true'] { border-color: var(--accent); color: var(--accent); }
h3 { margin: 16px 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
s { color: var(--muted); }

.app { position: relative; height: 100%; overflow: hidden; }
.map { position: absolute; inset: 0; }

.topbar {
  position: absolute; top: 0; left: 0; right: 0; z-index: 2;
  display: flex; gap: 8px; align-items: center;
  padding: calc(8px + env(safe-area-inset-top)) 10px 8px;
  pointer-events: none;
}
.topbar > * { pointer-events: auto; }
.searchbox { flex: 1; text-align: left; background: var(--surface); color: var(--muted); padding: 11px 14px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3); }
.fresh { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 6px 10px; font-size: 12px; max-width: 46%; }
.fresh.ok { color: var(--ok); }
.fresh.warn { color: var(--warn); }

.bottombar {
  position: absolute; left: 10px; right: 10px; bottom: calc(26px + env(safe-area-inset-bottom)); z-index: 2;
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}
.bottombar .count { margin-left: auto; color: var(--muted); font-size: 12px; padding-right: 4px; }

.sheet {
  position: absolute; left: 0; right: 0; bottom: 0; z-index: 3;
  background: var(--surface); border-top: 1px solid var(--border); border-radius: 16px 16px 0 0;
  padding: 12px 14px calc(14px + env(safe-area-inset-bottom));
  max-height: 46%; overflow-y: auto; box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.35);
}
.sheet.expanded { max-height: 82%; }
.sheet-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.train-title { font-size: 18px; margin-right: 8px; }
.trip { display: flex; gap: 8px; align-items: baseline; margin: 10px 0 6px; font-weight: 600; flex-wrap: wrap; }
.trip .arrow { color: var(--muted); }
.progress { height: 6px; background: var(--surface-2); border-radius: 3px; overflow: hidden; }
.progress > div { height: 100%; background: var(--accent); }
.next { margin: 10px 0 0; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }
.notice { margin: 10px 0 0; padding: 8px 10px; border-radius: 8px; background: var(--surface-2); }
.notice.bad { color: var(--bad); }
.notice.warn { color: var(--warn); }

.stops { list-style: none; margin: 12px 0 0; padding: 0; }
.stop { display: flex; gap: 10px; align-items: baseline; padding: 7px 0 7px 14px; border-left: 3px solid var(--border); }
.stop.pasada { border-left-color: var(--accent); color: var(--muted); }
.stop.proxima { border-left-color: var(--accent); font-weight: 600; }
.stop.suprimida { border-left-color: var(--bad); }
.stop.suprimida .link { text-decoration: line-through; }
.time { min-width: 96px; font-variant-numeric: tabular-nums; }

.panel { position: absolute; inset: 0; z-index: 5; display: flex; flex-direction: column; background: var(--bg); }
.panel-head {
  display: flex; gap: 8px; align-items: center;
  padding: calc(8px + env(safe-area-inset-top)) 10px 8px; background: var(--surface); border-bottom: 1px solid var(--border);
}
.panel-head input { flex: 1; background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; min-width: 0; }
.panel-body { flex: 1; overflow-y: auto; padding: 8px 12px calc(16px + env(safe-area-inset-bottom)); }
.tabs { display: flex; background: var(--surface); border-bottom: 1px solid var(--border); }
.tabs button { flex: 1; border: 0; border-radius: 0; background: none; padding: 12px; border-bottom: 3px solid transparent; }
.tabs button[aria-selected='true'] { border-bottom-color: var(--accent); color: var(--accent); }

.row {
  display: flex; gap: 10px; align-items: center; justify-content: space-between; width: 100%;
  padding: 12px 4px; text-align: left; background: none; border: 0; border-bottom: 1px solid var(--border); border-radius: 0;
}
.board-row { align-items: flex-start; }
.board-row small { display: block; }
.grow { flex: 1; min-width: 0; }
.fav { border-bottom: 1px solid var(--border); padding-bottom: 8px; }
.fav .row { border-bottom: 0; }
.avisos { display: flex; gap: 12px; flex-wrap: wrap; font-size: 13px; color: var(--muted); padding: 0 4px; }
.avisos label { display: flex; gap: 4px; align-items: center; }

.chip { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: var(--surface-2); border: 1px solid var(--border); white-space: nowrap; }
.delay-ok { color: var(--ok); }
.delay-warn { color: var(--warn); }
.delay-bad { color: var(--bad); }
.delay-none { color: var(--muted); }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.icon-btn { background: none; border: 0; padding: 6px 10px; font-size: 18px; }
.link { background: none; border: 0; padding: 0; color: var(--accent); text-align: left; }
.link:disabled { color: var(--text); opacity: 1; }
.muted { color: var(--muted); }
.small { font-size: 12px; }

.toast {
  position: absolute; left: 50%; bottom: 110px; transform: translateX(-50%); z-index: 9;
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; max-width: 90%;
}

@media (min-width: 760px) {
  .sheet { left: 12px; right: auto; bottom: 12px; width: 400px; border-radius: 16px; border: 1px solid var(--border); max-height: 60%; }
  .sheet.expanded { max-height: 88%; }
  .panel { left: 0; right: auto; width: 420px; border-right: 1px solid var(--border); }
  .bottombar { right: auto; }
}
```

- [ ] **Step 4: Verificar compilación y pruebas**

Run: `npm test` → en verde. Run: `npm run build` → sin errores.

- [ ] **Step 5: Verificación en el navegador (la hace el coordinador)**

Con la API en marcha en `http://localhost:8090`, arrancar `npm run dev` y abrir `http://localhost:5180`. Comprobar, anotando lo que falle:
1. El mapa de España carga en tema oscuro y aparecen cientos de trenes como flechas de colores (rosa, naranja y colores de línea de Cercanías).
2. Arriba a la derecha pone «hace N s» en verde y el contador se renueva cada 15 s. Los trenes se desplazan suavemente.
3. Al tocar un tren se abre la ficha, se dibuja su recorrido (tramo hecho continuo, pendiente discontinuo, paradas como puntos) y la URL pasa a `/t/<id>`. Recargar la página en esa URL vuelve a abrir el mismo tren.
4. «Paradas» despliega la lista con horas; «Ruta» encuadra el recorrido; «Seguir» mantiene el tren centrado; ✕ cierra y la URL vuelve a `/`.
5. Buscar «atocha» lista estaciones; al abrir una se ve el panel con pestañas Salidas y Llegadas, y las filas con tren en circulación abren su ficha.
6. Buscar un número de tren visible en el mapa lo encuentra.
7. Filtros: desmarcar Cercanías quita esos trenes del mapa y el contador baja; «Tema claro» cambia el mapa y la interfaz; «Mostrar vías» superpone OpenRailwayMap.
8. Favoritos: marcar un tren como favorito desde su ficha y verlo en el panel de Favoritos con sus cuatro casillas de aviso.
9. No hay errores en la consola del navegador (salvo teselas que tarden).
10. A 375 px de ancho (móvil) la ficha y los paneles se usan sin desbordes.

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/main.tsx web/src/styles.css
git commit -m "feat(web): composición de la app, estilos y registro del service worker"
```

---

### Task 13: Docker, nginx y prueba de la PWA instalada

**Files:**
- Create: `web/Dockerfile`, `web/nginx.conf`, `web/.dockerignore`, `README.md` (raíz)
- Modify: `docker-compose.yml` (añadir el servicio `web`)

- [ ] **Step 1: `web/nginx.conf`**

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;

  # La API vive en el contenedor "api". Sin compresión aquí: nginx debilitaría el ETag de /api/trains.
  location /api/ {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
  }

  # El service worker y la página no deben quedarse en caché del navegador.
  location = /sw.js { add_header Cache-Control "no-cache"; }
  location = /index.html { add_header Cache-Control "no-cache"; }

  # Los ficheros con huella en el nombre no cambian nunca.
  location /assets/ { add_header Cache-Control "public, max-age=31536000, immutable"; }

  # Rutas de la app (/t/..., /s/...): las resuelve el navegador.
  location / { try_files $uri /index.html; }
}
```

- [ ] **Step 2: `web/Dockerfile` y `web/.dockerignore`**

`web/Dockerfile`:
```dockerfile
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
```

`web/.dockerignore`:
```
node_modules
dist
```

- [ ] **Step 3: Servicio `web` en `docker-compose.yml`**

Añadir al final del fichero, al mismo nivel que `api` (dentro de `services:`):
```yaml
  web:
    build: ./web
    restart: unless-stopped
    depends_on:
      - api
    ports:
      # Puerto del equipo configurable: el 8080 suele estar ocupado por otros proyectos.
      - "${WEB_PORT:-8091}:80"
```

- [ ] **Step 4: Arrancar**

Comprobar antes que el puerto 8091 está libre (`netstat -ano | grep ":8091 "` no debe devolver nada). Si está ocupado, no parar nada: elegir otro puerto con `WEB_PORT` y decirlo en el informe.

```bash
docker compose up -d --build web
```
```bash
docker compose ps
```
Expected: `web` en estado `Up` y `api` en `healthy`. No tocar contenedores de otros proyectos.

- [ ] **Step 5: Verificar el servidor**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8091/
```
Expected: `200`

```bash
curl -s http://localhost:8091/api/health
```
Expected: JSON con `trenes` mayor que 0 (el proxy de nginx llega a la API).

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8091/t/LD:00000
```
Expected: `200` (nginx devuelve la app para las rutas internas).

```bash
curl -s -D - -o /dev/null http://localhost:8091/api/trains | grep -i etag
```
Expected: una cabecera `ETag` con comillas dobles y **sin** el prefijo `W/`. Repetir la petición con `-H 'If-None-Match: <ese valor>'` debe devolver `304`.

```bash
curl -s -D - -o /dev/null http://localhost:8091/sw.js | grep -i cache-control
```
Expected: `Cache-Control: no-cache`

- [ ] **Step 6: `README.md`** (raíz)

````markdown
# TrainRadar24h

Mapa en tiempo real de los trenes de Renfe en España. Uso personal.

Datos: Renfe (CC BY 4.0). Mapa: © OpenStreetMap, © CARTO, © OpenRailwayMap.

## Arrancar

```bash
docker compose up -d --build
```

- App: http://localhost:8091
- API: http://localhost:8090/api/health

El primer arranque descarga los horarios de Renfe (unos 16 MB) y tarda uno o dos minutos. Los puertos se cambian con las variables `WEB_PORT` y `API_PORT`.

## Avisos push

1. Generar las claves una vez: `api/.venv/Scripts/python api/scripts/gen_vapid.py data`
2. Copiar `.env.example` a `.env` y rellenar `VAPID_PUBLIC_KEY` (la imprime el paso anterior) y `VAPID_SUBJECT` (una dirección de contacto con formato `mailto:...`).
3. Reiniciar: `docker compose up -d`
4. En la app: Favoritos → «Activar» avisos, y marcar un tren como favorito.

Los avisos, la instalación como app y la geolocalización solo funcionan en HTTPS o en `localhost`.

## Usarla desde el móvil

Desde el móvil, `http://<IP-del-PC>:8091` abre la app, pero sin avisos, sin instalación y sin geolocalización, porque no es HTTPS. Para tenerlos hay que publicar el puerto 8091 con HTTPS, por ejemplo con un túnel (Cloudflare Tunnel, Tailscale Funnel) o con un proxy inverso con certificado (Caddy) en el servidor definitivo. Publicar la app en internet es decisión de quien la despliega.

## Desarrollo

```bash
cd api && .venv/Scripts/python -m pytest -q
```
```bash
cd web && npm test && npm run dev
```

`npm run dev` sirve la app en http://localhost:5180 y reenvía `/api` a la API del puerto 8090.

## Documentación

- Diseño: `docs/superpowers/specs/`
- Planes de implementación: `docs/superpowers/plans/`
````

- [ ] **Step 7: Verificación de la PWA en el navegador (la hace el coordinador)**

Abrir `http://localhost:8091` y comprobar:
1. La app funciona igual que en la tarea 12 (mapa, ficha, búsqueda, panel, filtros, favoritos).
2. El service worker queda registrado y activo (en la consola: `navigator.serviceWorker.getRegistration()` devuelve un registro con `active`).
3. El manifiesto se carga sin errores y el navegador ofrece instalar la app.
4. Favoritos → «Activar»: si `VAPID_SUBJECT` sigue vacío en `.env`, el alta en el navegador funciona pero el servidor no enviará avisos. Anotarlo en el informe; no inventar una dirección.
5. Con la red desconectada (modo sin conexión de las herramientas de desarrollo), recargar: la app abre, muestra los últimos trenes guardados y el indicador pasa a «Sin conexión».

- [ ] **Step 8: Commit**

```bash
git add web/Dockerfile web/nginx.conf web/.dockerignore docker-compose.yml README.md
git commit -m "feat: contenedor nginx de la PWA con proxy a la API y README"
```

---

## Cobertura del spec

| Sección del spec | Tarea |
|---|---|
| §6.1 Mapa (base, vías, frescura, barra inferior, iconos, animación, etiqueta) | 2, 4, 8, 12 |
| §6.2 Ficha del tren (compacta, expandida, favorito, seguir, ruta, compartir) | 5, 9, 12 |
| §6.3 Búsqueda y «estaciones cerca de mí» | 6, 10 |
| §6.4 Panel de estación | 10 |
| §6.5 Filtros (guardados en localStorage) | 3, 11 |
| §6.6 Favoritos con interruptores de aviso | 7, 11 |
| §6 PWA: manifiesto, service worker, sin conexión, `device_id` | 6, 7, 11, 12 |
| §7 Avisos push en el navegador | 11 |
| §7 Requisito de HTTPS para el móvil | 13 (README) |
| §8 Errores en la app (mantener datos, indicador) | 2, 7 |
| §9 Pruebas de frontend | 2–6, 11 |
