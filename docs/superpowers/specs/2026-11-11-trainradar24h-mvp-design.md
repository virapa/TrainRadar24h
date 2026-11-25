# TrainRadar24h · Diseño del MVP

Fecha: 2026-11-11 · Estado: aprobado por secciones, pendiente de revisión final

## 1. Objetivo y alcance

App personal para ver en un mapa los trenes de Renfe en España en tiempo real.

- **Uso:** personal o interno. Sin cuentas, sin monetización y sin publicar en tiendas.
- **Plataforma:** PWA instalable (Vite + React + TypeScript + MapLibre GL JS).
- **Servidor:** Python 3.12 + FastAPI en Docker. Se prueba en Docker Desktop local y después se migra a un servidor propio con Docker.
- **Dentro del MVP:**
  1. Mapa en vivo con ficha del tren y búsqueda.
  2. Panel de estación (salidas y llegadas).
  3. Favoritos y avisos Web Push.
- **Fuera del MVP:** histórico y playback, otros operadores (FGC, Euskotren, FGV…), capa de limitaciones de Adif, widget, cuentas, AR/3D y horas de silencio en los avisos.

## 2. Fuentes de datos (licencia CC BY 4.0, Renfe)

| Uso | URL | Refresco |
|---|---|---|
| Posiciones AV/LD/MD | `https://gtfsrt.renfe.com/vehicle_positions_LD.pb` | 15 s |
| Retrasos AV/LD/MD | `https://gtfsrt.renfe.com/trip_updates_LD.pb` | 30 s |
| Posiciones Cercanías | `https://gtfsrt.renfe.com/vehicle_positions.pb` | 20 s |
| Retrasos Cercanías | `https://gtfsrt.renfe.com/trip_updates.pb` | ~20–30 s (no documentado) |
| Horarios AV/LD/MD | `https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip` (~0,7 MB) | diario |
| Horarios Cercanías | `https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip` (~15,5 MB) | diario |

Hechos comprobados el 2026-11-11:
- Los feeds **no tienen CORS**, así que el navegador no puede leerlos directamente y el servidor es obligatorio.
- AV/LD/MD: 104 de 104 `tripId` en vivo existen en `trips.txt`. Hay `stopId` que solo existen en el GTFS de Cercanías (por ejemplo `04040` Zaragoza Delicias), así que **la tabla de estaciones une ambos ficheros**.
- Cercanías: 114 de 137 `tripId` casan, un 83 %. Los demás se muestran con ficha reducida usando el `label` (`C5-35903-PLATF.(3)`).
- El `label` de Cercanías lleva línea, número y andén. El GTFS de Cercanías trae `shapes.txt`, el de AV/LD/MD no.
- Rarezas: nombres de columna y valores rellenos de espacios, ficheros sin BOM y el de AV/LD/MD en **cp1252** (no UTF-8). AV/LD/MD usa `calendar` + `calendar_dates`. Cercanías solo `calendar`.
- La marca de tiempo del feed LD iba unos 60 min por detrás de la de Cercanías. Hay que vigilar la frescura de cada feed.
- Las cuatro URL `.pb` responden HTTP 200 (verificado el 2026-11-11). Los .pb ocupan entre 7 y 67 KB, frente a 35–250 KB en JSON.

## 3. Arquitectura

```
docker-compose
├─ api  (Python 3.12 · FastAPI · uvicorn · APScheduler)
│   ├─ gtfs_static/   descarga diaria (03:30 Europe/Madrid) → normaliza → SQLite
│   ├─ realtime/      cada 15 s: 4 feeds .pb → build_snapshot() → Snapshot en memoria
│   ├─ alerts/        tras cada snapshot: diff(prev, curr, favoritos) → Web Push
│   ├─ api/           REST (ver §5)
│   └─ /data/app.db   SQLite en volumen Docker: GTFS + favoritos + suscripciones + estado de avisos
└─ web  (nginx sirviendo la build de Vite; proxy /api → api:8000)
```

### Unidades

| Unidad | Responsabilidad | Interfaz | Depende de |
|---|---|---|---|
| `gtfs_static.loader` | Descargar el zip y validar su tamaño y estructura | `fetch(url) -> bytes` | red |
| `gtfs_static.normalize` | Limpiar cabeceras y valores, detectar la codificación (utf-8-sig y si no cp1252) y unir estaciones | `normalize(zip_bytes, source) -> Tables` | — |
| `gtfs_static.store` | Volcar las tablas en SQLite con un cambio atómico (tablas temporales y renombrado) | `store(tables, db)` | SQLite |
| `realtime.fetch` | Descargar y decodificar los .pb con `gtfs-realtime-bindings` | `fetch_feeds() -> Feeds` | red |
| `realtime.snapshot` | **Función pura**: cruza los feeds con el GTFS y produce los trenes | `build_snapshot(feeds, gtfs_repo, prev) -> Snapshot` | interfaz de solo lectura de `gtfs_repo` |
| `alerts.diff` | **Función pura**: avisos a enviar | `diff(prev, curr, subs, notified) -> list[Alert]` | — |
| `alerts.push` | Enviar con `pywebpush` (VAPID) y borrar las suscripciones caducadas (404/410) | `send(alert)` | red, SQLite |
| `api` | Capa HTTP fina sobre el snapshot y SQLite | rutas §5 | las anteriores |
| `web/apiClient` | Pedir datos cada 15 s con `If-None-Match` | `useTrains()`, `getTrain(id)`… | `/api` |
| `web/MapView` | Mapa, iconos, animación, trazas | props: trenes, selección | MapLibre |
| `web/TrainSheet` | Ficha en dos niveles | `trainId` | apiClient |
| `web/Search`, `web/StationBoard`, `web/Favorites`, `web/Filters` | Pantallas §6 | — | apiClient |

## 4. Flujo de datos en tiempo real

Cada 15 s:
1. Descarga en paralelo de los 4 feeds. Si uno falla se reutiliza su último valor bueno, marcado como `stale`.
2. Por cada `VehiclePosition`:
   - `id = "<LD|CER>:<vehicle.id>"`.
   - Si `tripId` está en `trips`: se toman ruta (`route_short_name`, por ejemplo AVE/ALVIA/C1), color, número (`trip_short_name` o el número extraído del `trip_id`), origen y destino (primera y última parada de `stop_times`) y la lista de paradas ordenada.
   - Si no casa: `casado_con_horario=false`, y la línea y el número se sacan del `label` (regex `^(?P<linea>[^-]+)-(?P<num>\d+)(?:-PLATF\.\((?P<anden>[^)]+)\))?`).
3. Retrasos (`TripUpdate` con el mismo `tripId`):
   - La hora estimada es `hora_prog + delay`, y el último `delay` conocido se propaga a las paradas siguientes.
   - `scheduleRelationship=SKIPPED` marca la parada como suprimida.
   - Viaje `CANCELED` deja el tren con estado cancelado.
4. Próxima parada: el `stopId` del vehículo y, si falta, la primera parada no pasada según la hora estimada. Progreso = índice de la próxima parada / total de paradas.
5. Rumbo: ángulo desde la posición anterior del mismo `id` en `prev`. Si se ha movido menos de 30 m, se conserva el rumbo anterior.
6. Andén: solo el del `label` de Cercanías. En los demás, `null`.
7. Se publica el nuevo `Snapshot` con cambio atómico de referencia y se calcula `etag = hash(contenido)`.

Las horas se gestionan en `Europe/Madrid`. Las `stop_times` de más de 24:00 se interpretan como día siguiente. Los servicios activos se calculan con `calendar` y `calendar_dates` para la fecha de servicio.

## 5. API REST

| Método y ruta | Respuesta |
|---|---|
| `GET /api/trains` | Lista ligera para el mapa: `id, numero, servicio, linea, color, lat, lon, rumbo, retraso_min, estado` y `feeds: {LD:{edad_s}, CER:{edad_s}}`. Soporta `ETag` y devuelve 304. |
| `GET /api/trains/{id}` | Ficha completa (modelo `Train` §5.1) más `paradas[]: {id, nombre, lat, lon, hora_prog, hora_est, estado: pasada\|proxima\|pendiente\|suprimida}` y `shape` (lista de [lon,lat]) si existe. Sin `shape`, se usa la polilínea de las paradas. |
| `GET /api/search?q=` | `{trenes:[…], estaciones:[…]}`. Búsqueda numérica por número de tren. Por texto, estaciones sin acentos ni mayúsculas (máximo 20). |
| `GET /api/stations/near?lat=&lon=` | Las 10 estaciones más cercanas. |
| `GET /api/stations/{id}/board?tipo=salidas\|llegadas` | Ventana desde hace 30 min hasta 3 h: `hora_prog, hora_est, destino/origen, servicio, numero, anden, estado, train_id` (si circula). |
| `GET/PUT/DELETE /api/favorites` | Encabezado `X-Device-Id`. Favoritos `{tipo: tren\|estacion, ref, avisos:{retraso, cancelacion, anden, salida}}`. |
| `POST/DELETE /api/push/subscription` | Guarda o borra la suscripción Web Push del dispositivo. `GET /api/push/vapid-public-key`. |
| `GET /api/health` | Edad de cada feed, fecha de los horarios cargados y número de trenes. |

### 5.1 Modelo `Train`
```json
{ "id": "LD:03304", "numero": "03304", "servicio": "AVE", "linea": null,
  "color": "#F2F5F5", "lat": 41.63, "lon": 0.50, "rumbo": 245, "estado": "IN_TRANSIT_TO",
  "origen": "Madrid-Puerta de Atocha", "destino": "Barcelona-Sants",
  "proxima_parada": {"id": "04040", "nombre": "Zaragoza Delicias", "hora_prog": "12:41", "hora_est": "12:46"},
  "retraso_min": 5, "anden": null, "progreso": 0.42, "casado_con_horario": true, "ts": 1794392674 }
```

## 6. Pantallas (PWA)

Modo oscuro por defecto y claro opcional. Sin anuncios ni bloqueos de pago. Atribución «Datos: Renfe (CC BY 4.0) · © OpenStreetMap · OpenRailwayMap» siempre visible en el mapa.

1. **Mapa:**
   - MapLibre con mapa base OSM y la capa de vías de OpenRailwayMap (activable).
   - Arriba: buscador y frescura de los datos («hace 12 s»), con aviso si algún feed tiene más de 3 min.
   - Barra flotante inferior: Filtros, Favoritos, Mi ubicación.
   - Icono por servicio, girado según el rumbo y animado de forma lineal entre posiciones durante unos 15 s.
   - Etiqueta con el número del tren con zoom ≥ 10 o con menos de 150 trenes visibles.
2. **Ficha del tren (bottom sheet):**
   - **Compacta:** servicio y número, origen → destino, barra de progreso, próxima parada con hora estimada, retraso en color (verde < 5, ámbar 5–14, rojo ≥ 15 min) y andén.
   - **Expandida:** línea temporal de paradas.
   - Acciones: ★ Favorito, Seguir (la cámara sigue al tren), Ruta (zoom al recorrido, tramo hecho sólido y pendiente discontinuo), Compartir (Web Share: «AVE 03304 Madrid → Barcelona · +5 min» con enlace `/t/{id}`).
3. **Búsqueda:** un campo con resultados agrupados en Trenes y Estaciones, más el atajo «Estaciones cerca de mí».
4. **Panel de estación:** cabecera con ★, pestañas Salidas y Llegadas, y filas con hora, destino u origen, servicio y número, andén y estado o retraso. Al tocar una fila se abre la ficha del tren si circula.
5. **Filtros:** AV/LD, MD, Cercanías por núcleo y «solo con retraso». Se guardan en localStorage.
6. **Favoritos:** trenes (por número, cualquier día) y estaciones, con interruptores de aviso por favorito.

**PWA:**
- `manifest` instalable.
- Service worker con caché de la estructura de la app (shell), recepción de push y clic que abre `/t/{id}`.
- Sin conexión se muestra el último snapshot con la etiqueta «sin conexión».
- `device_id` (UUID) en localStorage.

## 7. Avisos push

- Tipos por favorito de tren:
  - retraso ≥ 5 min y cada vez que aumente 5 min más
  - cancelación o parada suprimida
  - cambio de andén
  - salida en 15 min desde su origen (si el tren está programado hoy)
- Sin repeticiones: la tabla `notified(device_id, train_ref, fecha_servicio, tipo, valor)`.
- Las suscripciones que responden 404 o 410 se borran.
- **Requisito de entorno:** los push, el service worker y la geolocalización necesitan contexto seguro.
  - En el PC funciona con `http://localhost`.
  - Desde el móvil hace falta HTTPS: túnel (Cloudflare Tunnel o Tailscale) durante las pruebas, y Caddy con Let's Encrypt en el servidor definitivo.

## 8. Errores y resiliencia

- **Feed caído o corrupto:** se mantiene el último bueno, se marca `stale`, hay log y se reintenta con espera exponencial (máximo 2 min).
- **Horarios:** si falla la descarga o la validación, se conserva la versión anterior. La carga es atómica.
- **App:** si falla una petición se mantienen los datos y aparece un indicador. Los reintentos siguen el ciclo de 15 s.
- `/api/health` es el health check del contenedor en Docker.

## 9. Pruebas

- **Backend (pytest):**
  - Normalizador con zips de muestra que reproducen las rarezas reales: espacios y cp1252.
  - `build_snapshot` con feeds reales grabados el 2026-11-11, guardados en `tests/fixtures/`.
  - Propagación de retrasos, paradas suprimidas y el parseo del `label`.
  - `alerts.diff` con secuencias de snapshots.
  - Endpoints con `TestClient`, incluido el 304 con `ETag`.
- **Frontend (Vitest):** `apiClient`, formateo de horas y retrasos, filtros. Prueba manual en el navegador y en el móvil a través del túnel.

## 10. Estructura del repositorio

```
TrainRadar24h/
├─ docker-compose.yml
├─ api/   (pyproject.toml, app/{gtfs_static,realtime,alerts,api}, tests/)
├─ web/   (package.json, vite.config.ts, src/{api,components,map,pages,sw})
└─ docs/
```

## 11. Decisiones registradas

- Enfoque A: snapshot en el servidor y peticiones REST cada 15 s con `ETag`, sin WebSocket ni SSE.
- SQLite en lugar de Postgres: un solo usuario y sin histórico.
- MapLibre y OSM en lugar de Google Maps: sin claves ni costes.
- Sin cuentas: `device_id` local.
