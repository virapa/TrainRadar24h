# TrainRadar24h · Servidor (API) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servidor FastAPI en Docker que lee los feeds GTFS-RT de Renfe cada 15 s, los cruza con los horarios GTFS en SQLite y expone una API REST con trenes en vivo, búsqueda, panel de estación, favoritos y avisos Web Push.

**Architecture:** Un proceso FastAPI con dos bucles asyncio: uno refresca los horarios GTFS a diario y otro construye cada 15 s un `Snapshot` en memoria con una función pura (`build_snapshot`). Las rutas HTTP solo leen el snapshot y SQLite. Tras cada snapshot, otra función pura (`diff`) decide qué avisos push enviar.

**Tech Stack:** Python ≥ 3.12, FastAPI, uvicorn, httpx, gtfs-realtime-bindings, pywebpush, SQLite (stdlib), pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-11-trainradar24h-mvp-design.md`

**Alcance de este plan:** solo el servidor (`api/`). La PWA (`web/`) va en un segundo plan, que se escribe cuando esta API esté funcionando, porque consume su contrato.

**Desviaciones del spec (deliberadas, más simples):**
- Dos ficheros SQLite en lugar de uno: `gtfs.db` (se regenera entero y se sustituye con `os.replace`, que es atómico) y `app.db` (favoritos, suscripciones, avisos enviados).
- Bucles `asyncio` en lugar de APScheduler. Los horarios se refrescan a partir de las 03:00 (hora de Madrid) si el fichero es de un día anterior.

**Convenciones:**
- Todos los comandos se ejecutan desde `api/` salvo que se indique otra cosa.
- Los feeds se manejan como diccionarios con la forma del JSON de Renfe (claves camelCase: `tripId`, `stopTimeUpdate`…). `MessageToDict` produce exactamente esa forma a partir del `.pb`, así que los JSON de `tests/fixtures/` sirven de datos de prueba.
- Fuentes: `"LD"` (Alta Velocidad, Larga y Media Distancia) y `"CER"` (Cercanías).
- Horas internas: segundos desde medianoche de la fecha de servicio (pueden pasar de 86400). Zona horaria: `Europe/Madrid`.

## Estructura de ficheros

```
TrainRadar24h/
├─ .gitignore
├─ docker-compose.yml
├─ .env.example
└─ api/
   ├─ pyproject.toml
   ├─ Dockerfile
   ├─ scripts/gen_vapid.py          genera las claves VAPID
   ├─ app/
   │  ├─ config.py                  Settings (URLs, rutas, claves)
   │  ├─ timeutil.py                MADRID, service_midnight, hhmm
   │  ├─ geo.py                     haversine_m, bearing
   │  ├─ state.py                   State (repo, snapshot, reloj)
   │  ├─ appdb.py                   favoritos, suscripciones, avisos enviados
   │  ├─ main.py                    create_app, bucles de fondo
   │  ├─ gtfs_static/
   │  │  ├─ normalize.py            leer CSV sucios de un zip
   │  │  ├─ store.py                construir gtfs.db
   │  │  ├─ repo.py                 consultas de solo lectura
   │  │  └─ loader.py               descargar, validar, refrescar
   │  ├─ realtime/
   │  │  ├─ models.py               Feed, Train, Snapshot
   │  │  ├─ snapshot.py             build_snapshot (pura)
   │  │  └─ fetch.py                descarga y decodificación .pb
   │  ├─ alerts/
   │  │  ├─ diff.py                 diff (pura)
   │  │  ├─ push.py                 envío Web Push
   │  │  └─ run.py                  process: une diff + push + appdb
   │  └─ api/
   │     ├─ trains.py               /health, /trains, /trains/{id}, /search
   │     ├─ stations.py             /stations/near, /stations/{id}/board
   │     └─ user.py                 /favorites, /push/*
   └─ tests/
      ├─ helpers.py                 mini-GTFS de prueba, make_zip, NOW
      ├─ conftest.py                fixtures gtfs_db, repo, client
      ├─ fixtures/*.json            feeds reales capturados el 2026-11-11 (ya existen)
      └─ test_*.py
```

---

### Task 0: Repositorio git

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Inicializar git y crear `.gitignore`** (desde la raíz del proyecto)

```bash
git init -b main
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
.pytest_cache/
*.egg-info/
data/
.env
node_modules/
dist/
```

- [ ] **Step 2: Commit inicial**

```bash
git add .gitignore docs api/tests/fixtures
git commit -m "docs: investigación, spec y plan del MVP; fixtures de feeds reales"
```

---

### Task 1: Esqueleto del paquete y utilidades

**Files:**
- Create: `api/pyproject.toml`, `api/app/__init__.py`, `api/app/gtfs_static/__init__.py`, `api/app/realtime/__init__.py`, `api/app/alerts/__init__.py`, `api/app/api/__init__.py`, `api/tests/__init__.py` (todos los `__init__.py` vacíos)
- Create: `api/app/config.py`, `api/app/timeutil.py`, `api/app/geo.py`
- Test: `api/tests/test_utils.py`

- [ ] **Step 1: `pyproject.toml` y entorno**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "trainradar-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "httpx>=0.27",
  "gtfs-realtime-bindings>=1.0",
  "protobuf>=4.25",
  "pywebpush>=2.0",
  "tzdata",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```
(En Linux/macOS: `.venv/bin/python`. En adelante, `pytest` significa `.venv/Scripts/python -m pytest`.)

- [ ] **Step 2: Test que falla** — `tests/test_utils.py`

```python
from datetime import date

from app.geo import bearing, haversine_m
from app.timeutil import hhmm, service_midnight


def test_service_midnight_and_hhmm():
    base = service_midnight(date(2026, 11, 11))
    assert hhmm(base + 11 * 3600 + 20 * 60) == "11:20"
    assert hhmm(base + 25 * 3600) == "01:00"  # pasa de medianoche


def test_haversine_and_bearing():
    assert 8300 < haversine_m(41.0, -2.0, 41.0, -1.9) < 8500
    assert abs(bearing(41.0, -2.0, 41.0, -1.9) - 90) < 1
    assert abs(bearing(41.0, -2.0, 42.0, -2.0) - 0) < 1
```

- [ ] **Step 3: Ejecutar y ver que falla**

Run: `pytest tests/test_utils.py -v` → FAIL (`ModuleNotFoundError: app.geo`)

- [ ] **Step 4: Implementación**

`app/timeutil.py`:
```python
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def service_midnight(d: date) -> float:
    """Timestamp de las 00:00 (hora de Madrid) de la fecha de servicio."""
    return datetime.combine(d, time(0), MADRID).timestamp()


def hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts, MADRID).strftime("%H:%M")


def madrid_date(ts: float) -> date:
    return datetime.fromtimestamp(ts, MADRID).date()
```

`app/geo.py`:
```python
from math import atan2, cos, degrees, radians, sin, sqrt


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = p2 - p1, radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 6371000 * 2 * atan2(sqrt(a), sqrt(1 - a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Rumbo en grados (0 = norte, 90 = este) de 1 a 2."""
    p1, p2, dl = radians(lat1), radians(lat2), radians(lon2 - lon1)
    y = sin(dl) * cos(p2)
    x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    return (degrees(atan2(y, x)) + 360) % 360
```

`app/config.py`:
```python
import os
from dataclasses import dataclass, field
from pathlib import Path

RT = "https://gtfsrt.renfe.com"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("DATA_DIR", "./data")))
    poll_seconds: int = 15
    gtfs_min_bytes: int = 100_000
    feed_urls: dict[str, str] = field(default_factory=lambda: {
        "LD_vp": f"{RT}/vehicle_positions_LD.pb",
        "LD_tu": f"{RT}/trip_updates_LD.pb",
        "CER_vp": f"{RT}/vehicle_positions.pb",
        "CER_tu": f"{RT}/trip_updates.pb",
    })
    gtfs_urls: dict[str, str] = field(default_factory=lambda: {
        "LD": "https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip",
        "CER": "https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip",
    })
    vapid_private_key: str = field(default_factory=lambda: os.environ.get("VAPID_PRIVATE_KEY", ""))
    vapid_public_key: str = field(default_factory=lambda: os.environ.get("VAPID_PUBLIC_KEY", ""))
    vapid_subject: str = field(default_factory=lambda: os.environ.get("VAPID_SUBJECT", ""))

    @property
    def gtfs_db(self) -> Path:
        return self.data_dir / "gtfs.db"

    @property
    def app_db(self) -> Path:
        return self.data_dir / "app.db"
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `pytest tests/test_utils.py -v` → 2 passed

- [ ] **Step 6: Commit**

```bash
git add api/pyproject.toml api/app api/tests
git commit -m "feat(api): esqueleto del paquete, configuración y utilidades de tiempo y geometría"
```

---

### Task 2: Normalizador de CSV GTFS

Los ficheros de Renfe traen cabeceras y valores rellenos de espacios, y el de LD está en cp1252.

**Files:**
- Create: `api/tests/helpers.py`, `api/app/gtfs_static/normalize.py`
- Test: `api/tests/test_normalize.py`

- [ ] **Step 1: Datos de prueba compartidos** — `tests/helpers.py`

```python
import io
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

# Miércoles 11-nov-2026, 11:00 hora de Madrid
NOW = datetime(2026, 11, 11, 11, 0, tzinfo=ZoneInfo("Europe/Madrid")).timestamp()
PAD = " " * 40

LD_FILES = {
    "routes.txt": (
        f"route_id,agency_id,route_short_name,route_long_name,route_type,route_color,route_text_color{PAD}\n"
        f"R1,1071,AVE,,2,FF0000,{PAD}\n"
    ),
    "trips.txt": (
        f"route_id,service_id,trip_id,trip_headsign,trip_short_name,shape_id{PAD}\n"
        f"R1,S1,0330412026-11-11,,03304,{PAD}\n"
    ),
    "stops.txt": (
        f"stop_id,stop_name,stop_lat,stop_lon{PAD}\n"
        "60000,Madrid-Puerta de Atocha,40.4066,-3.6902\n"
        "17000,Madrid-Chamartín-Clara Campoamor,40.4712,-3.6830\n"
        "04040,Zaragoza Delicias,41.6587,-0.9113\n"
        f"71801,Barcelona-Sants,41.3790,2.1400{PAD}\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "0330412026-11-11,10:00:00,10:00:00,60000,1\n"
        "0330412026-11-11,11:20:00,11:22:00,04040,2\n"
        "0330412026-11-11,12:45:00,12:45:00,71801,3\n"
    ),
    "calendar.txt": (
        f"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date{PAD}\n"
        f"S1,1,1,1,1,1,1,1,20261101,20261231{PAD}\n"
    ),
    "calendar_dates.txt": "service_id,date,exception_type\nS1,20261225,2\n",
}

CER_FILES = {
    "routes.txt": (
        "route_id,route_short_name,route_long_name,route_type,route_color\n"
        "10T0001C1  ,C1  ,Principe Pio -Aeropuerto-T4 ,2,75B6E0\n"
    ),
    "trips.txt": (
        "route_id,service_id,trip_id,trip_headsign,shape_id\n"
        "10T0001C1,1014X,1014X19799C1,,10_C1\n"
    ),
    "stops.txt": (
        "stop_id,stop_name,stop_lat,stop_lon\n"
        "18002,Príncipe Pío,40.4210,-3.7200\n"
        "18000,Madrid-Atocha Cercanías,40.4065,-3.6895\n"
        "04040,Zaragoza Delicias,41.6586576,-0.9112693\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "1014X19799C1,10:00:00,10:00:00,18002,1\n"
        "1014X19799C1,10:10:00,10:10:00,18000,2\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "1014X,0,0,1,0,0,0,0,20261111,20261111\n"
    ),
    "shapes.txt": (
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
        "10_C1,40.4210,-3.7200,1\n"
        "10_C1,40.4065,-3.6895,2\n"
    ),
}


def make_zip(files: dict[str, str], encoding: str = "utf-8") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text.encode(encoding))
    return buf.getvalue()


def gtfs_sources() -> dict[str, bytes]:
    """LD en cp1252 (como el real) y CER en UTF-8."""
    return {"LD": make_zip(LD_FILES, "cp1252"), "CER": make_zip(CER_FILES)}
```

- [ ] **Step 2: Test que falla** — `tests/test_normalize.py`

```python
import io
import zipfile

from app.gtfs_static.normalize import iter_table, norm_text, parse_time
from tests.helpers import CER_FILES, LD_FILES, make_zip


def _zf(raw: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(raw))


def test_strips_padded_headers_and_values():
    rows = list(iter_table(_zf(make_zip(LD_FILES, "cp1252")), "calendar.txt"))
    assert rows == [{
        "service_id": "S1", "monday": "1", "tuesday": "1", "wednesday": "1", "thursday": "1",
        "friday": "1", "saturday": "1", "sunday": "1", "start_date": "20261101", "end_date": "20261231",
    }]


def test_decodes_cp1252_and_utf8():
    ld = list(iter_table(_zf(make_zip(LD_FILES, "cp1252")), "stops.txt"))
    cer = list(iter_table(_zf(make_zip(CER_FILES)), "stops.txt"))
    assert ld[1]["stop_name"] == "Madrid-Chamartín-Clara Campoamor"
    assert cer[0]["stop_name"] == "Príncipe Pío"


def test_utf8_bom_is_removed():
    rows = list(iter_table(_zf(make_zip({"a.txt": "﻿x,y\n1,2\n"})), "a.txt"))
    assert rows == [{"x": "1", "y": "2"}]


def test_missing_file_yields_nothing():
    assert list(iter_table(_zf(make_zip(CER_FILES)), "calendar_dates.txt")) == []


def test_parse_time():
    assert parse_time("10:00:00") == 36000
    assert parse_time("25:10:30") == 90630
    assert parse_time(" 7:05:00 ") == 25500
    assert parse_time("") is None
    assert parse_time(None) is None


def test_norm_text():
    assert norm_text("  Madrid-Chamartín ") == "madrid-chamartin"
```

- [ ] **Step 3: Ejecutar y ver que falla**

Run: `pytest tests/test_normalize.py -v` → FAIL (`ModuleNotFoundError`)

- [ ] **Step 4: Implementación** — `app/gtfs_static/normalize.py`

```python
import csv
import io
import unicodedata
import zipfile
from collections.abc import Iterator


def decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def iter_table(zf: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    """Filas de un CSV del zip, con cabeceras y valores sin espacios sobrantes."""
    if name not in zf.namelist():
        return
    reader = csv.reader(io.StringIO(decode(zf.read(name))))
    header = [h.strip() for h in next(reader, [])]
    for row in reader:
        if row:
            yield {h: v.strip() for h, v in zip(header, row)}


def parse_time(value: str | None) -> int | None:
    """'HH:MM:SS' → segundos desde medianoche (HH puede ser ≥ 24)."""
    if not value or not value.strip():
        return None
    h, m, s = value.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def norm_text(text: str) -> str:
    """Minúsculas y sin acentos, para buscar."""
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `pytest tests/test_normalize.py -v` → 6 passed

- [ ] **Step 6: Commit**

```bash
git add api/app/gtfs_static/normalize.py api/tests/helpers.py api/tests/test_normalize.py
git commit -m "feat(api): normalizador de CSV GTFS (espacios, cp1252, BOM)"
```

---

### Task 3: Construir `gtfs.db`

**Files:**
- Create: `api/app/gtfs_static/store.py`, `api/tests/conftest.py`
- Test: `api/tests/test_store.py`

- [ ] **Step 1: Fixture** — `tests/conftest.py`

```python
import pytest

from app.gtfs_static.store import build_gtfs_db
from tests.helpers import gtfs_sources


@pytest.fixture
def gtfs_db(tmp_path):
    path = tmp_path / "gtfs.db"
    build_gtfs_db(path, gtfs_sources())
    return path
```

- [ ] **Step 2: Test que falla** — `tests/test_store.py`

```python
import sqlite3
from contextlib import closing

from app.gtfs_static.store import build_gtfs_db
from tests.helpers import gtfs_sources


def q(path, sql, *params):
    with closing(sqlite3.connect(path)) as con:
        return con.execute(sql, params).fetchall()


def test_tables_are_loaded(gtfs_db):
    assert q(gtfs_db, "SELECT COUNT(*) FROM trips") == [(2,)]
    assert q(gtfs_db, "SELECT short_name, color FROM routes WHERE source='CER'") == [("C1", "75B6E0")]
    assert q(gtfs_db, "SELECT arr, dep FROM stop_times WHERE trip_id='0330412026-11-11' AND seq=2") == [(40800, 40920)]
    assert q(gtfs_db, "SELECT days, start_date FROM calendar WHERE service_id='1014X'") == [("0010000", "20261111")]
    assert q(gtfs_db, "SELECT exception_type FROM calendar_dates") == [(2,)]
    assert q(gtfs_db, "SELECT COUNT(*) FROM shapes WHERE shape_id='10_C1'") == [(2,)]
    assert q(gtfs_db, "SELECT value IS NOT NULL FROM meta WHERE key='loaded_at'") == [(1,)]


def test_train_number(gtfs_db):
    assert q(gtfs_db, "SELECT numero FROM trips WHERE source='LD'") == [("03304",)]
    assert q(gtfs_db, "SELECT numero FROM trips WHERE source='CER'") == [("19799",)]


def test_stops_are_merged_without_duplicates(gtfs_db):
    assert q(gtfs_db, "SELECT COUNT(*) FROM stops") == [(6,)]
    assert q(gtfs_db, "SELECT name_norm FROM stops WHERE stop_id='17000'") == [("madrid-chamartin-clara campoamor",)]
    assert q(gtfs_db, "SELECT COUNT(*) FROM stops WHERE stop_id='04040'") == [(1,)]


def test_rebuild_replaces_previous_file(gtfs_db):
    build_gtfs_db(gtfs_db, gtfs_sources())
    assert q(gtfs_db, "SELECT COUNT(*) FROM trips") == [(2,)]
    assert not gtfs_db.with_suffix(".new").exists()
```

- [ ] **Step 3: Ejecutar y ver que falla**

Run: `pytest tests/test_store.py -v` → ERROR (`ModuleNotFoundError: app.gtfs_static.store`)

- [ ] **Step 4: Implementación** — `app/gtfs_static/store.py`

```python
import io
import os
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .normalize import iter_table, norm_text, parse_time

SCHEMA = """
CREATE TABLE stops(stop_id TEXT PRIMARY KEY, name TEXT, name_norm TEXT, lat REAL, lon REAL);
CREATE TABLE routes(source TEXT, route_id TEXT, short_name TEXT, long_name TEXT, color TEXT,
                    PRIMARY KEY(source, route_id));
CREATE TABLE trips(source TEXT, trip_id TEXT, route_id TEXT, service_id TEXT, numero TEXT, shape_id TEXT,
                   PRIMARY KEY(source, trip_id));
CREATE INDEX trips_numero ON trips(numero);
CREATE TABLE stop_times(source TEXT, trip_id TEXT, seq INTEGER, stop_id TEXT, arr INTEGER, dep INTEGER,
                        PRIMARY KEY(source, trip_id, seq)) WITHOUT ROWID;
CREATE INDEX stop_times_stop ON stop_times(stop_id, dep);
CREATE TABLE calendar(source TEXT, service_id TEXT, days TEXT, start_date TEXT, end_date TEXT,
                      PRIMARY KEY(source, service_id));
CREATE TABLE calendar_dates(source TEXT, service_id TEXT, date TEXT, exception_type INTEGER,
                            PRIMARY KEY(source, service_id, date));
CREATE TABLE shapes(shape_id TEXT, seq INTEGER, lat REAL, lon REAL, PRIMARY KEY(shape_id, seq)) WITHOUT ROWID;
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def train_number(row: dict[str, str]) -> str:
    """LD: trip_short_name. Cercanías: los dígitos que siguen al service_id dentro del trip_id."""
    if row.get("trip_short_name"):
        return row["trip_short_name"]
    trip_id, service_id = row["trip_id"], row.get("service_id", "")
    if service_id and trip_id.startswith(service_id):
        m = re.match(r"\d+", trip_id[len(service_id):])
        if m:
            return m.group()
    return ""


def _stop_times(source: str, zf: zipfile.ZipFile):
    for r in iter_table(zf, "stop_times.txt"):
        arr, dep = parse_time(r.get("arrival_time")), parse_time(r.get("departure_time"))
        if arr is None and dep is None:
            continue
        yield (source, r["trip_id"], int(r["stop_sequence"]), r["stop_id"],
               arr if arr is not None else dep, dep if dep is not None else arr)


def _load(con: sqlite3.Connection, source: str, zf: zipfile.ZipFile) -> None:
    con.executemany(
        "INSERT OR IGNORE INTO stops VALUES(?,?,?,?,?)",
        ((r["stop_id"], r["stop_name"], norm_text(r["stop_name"]), float(r["stop_lat"]), float(r["stop_lon"]))
         for r in iter_table(zf, "stops.txt") if r.get("stop_lat") and r.get("stop_lon")))
    con.executemany(
        "INSERT OR REPLACE INTO routes VALUES(?,?,?,?,?)",
        ((source, r["route_id"], r.get("route_short_name", ""), r.get("route_long_name", ""),
          r.get("route_color", "")) for r in iter_table(zf, "routes.txt")))
    con.executemany(
        "INSERT OR REPLACE INTO trips VALUES(?,?,?,?,?,?)",
        ((source, r["trip_id"], r["route_id"], r["service_id"], train_number(r), r.get("shape_id", ""))
         for r in iter_table(zf, "trips.txt")))
    con.executemany("INSERT OR REPLACE INTO stop_times VALUES(?,?,?,?,?,?)", _stop_times(source, zf))
    con.executemany(
        "INSERT OR REPLACE INTO calendar VALUES(?,?,?,?,?)",
        ((source, r["service_id"], "".join(r[d] for d in DAYS), r["start_date"], r["end_date"])
         for r in iter_table(zf, "calendar.txt")))
    con.executemany(
        "INSERT OR REPLACE INTO calendar_dates VALUES(?,?,?,?)",
        ((source, r["service_id"], r["date"], int(r["exception_type"]))
         for r in iter_table(zf, "calendar_dates.txt")))
    con.executemany(
        "INSERT OR REPLACE INTO shapes VALUES(?,?,?,?)",
        ((r["shape_id"], int(r["shape_pt_sequence"]), float(r["shape_pt_lat"]), float(r["shape_pt_lon"]))
         for r in iter_table(zf, "shapes.txt")))


def build_gtfs_db(path: Path, sources: dict[str, bytes]) -> None:
    """Construye la base en un fichero temporal y lo sustituye de forma atómica."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".new")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.executescript(SCHEMA)
        for source, raw in sources.items():
            _load(con, source, zipfile.ZipFile(io.BytesIO(raw)))
        con.execute("INSERT INTO meta VALUES('loaded_at', ?)", (datetime.now(timezone.utc).isoformat(),))
        con.commit()
    finally:
        con.close()
    os.replace(tmp, path)
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `pytest tests/test_store.py -v` → 4 passed

- [ ] **Step 6: Commit**

```bash
git add api/app/gtfs_static/store.py api/tests/conftest.py api/tests/test_store.py
git commit -m "feat(api): carga de GTFS en SQLite con sustitución atómica"
```

---

### Task 4: Repositorio de consultas GTFS

**Files:**
- Create: `api/app/gtfs_static/repo.py`
- Modify: `api/tests/conftest.py` (añadir fixture `repo`)
- Test: `api/tests/test_repo.py`

- [ ] **Step 1: Añadir fixture** — al final de `tests/conftest.py`

```python
from app.gtfs_static.repo import GtfsRepo


@pytest.fixture
def repo(gtfs_db):
    return GtfsRepo(gtfs_db)
```

- [ ] **Step 2: Test que falla** — `tests/test_repo.py`

```python
from datetime import date

D = date(2026, 11, 11)


def test_trip_with_stops(repo):
    t = repo.trip("LD", "0330412026-11-11")
    assert (t.numero, t.route_short, t.color) == ("03304", "AVE", "FF0000")
    assert [s.stop_id for s in t.stops] == ["60000", "04040", "71801"]
    assert (t.stops[1].name, t.stops[1].arr, t.stops[1].dep) == ("Zaragoza Delicias", 40800, 40920)
    assert repo.trip("LD", "no-existe") is None


def test_shape(repo):
    assert repo.shape("10_C1") == [[-3.72, 40.421], [-3.6895, 40.4065]]
    assert repo.shape("nada") == []


def test_search_stops_ignores_accents_and_case(repo):
    assert [s["id"] for s in repo.search_stops("CHAMARTIN")] == ["17000"]
    assert [s["id"] for s in repo.search_stops("príncipe")] == ["18002"]
    assert {s["id"] for s in repo.search_stops("madrid")} == {"60000", "17000", "18000"}


def test_near(repo):
    near = repo.near(40.4066, -3.6902, limit=2)
    assert {s["id"] for s in near} == {"60000", "18000"}
    assert near[0]["dist_m"] <= near[1]["dist_m"]


def test_board_departures_and_arrivals(repo):
    sal = repo.board("04040", D, 0, 86400, "salidas")
    assert len(sal) == 1
    assert (sal[0]["numero"], sal[0]["destino"], sal[0]["origen"], sal[0]["dep"]) == (
        "03304", "Barcelona-Sants", "Madrid-Puerta de Atocha", 40920)
    assert repo.board("71801", D, 0, 86400, "salidas") == []      # última parada: no sale
    assert len(repo.board("71801", D, 0, 86400, "llegadas")) == 1
    assert repo.board("60000", D, 0, 86400, "llegadas") == []     # primera parada: no llega


def test_board_respects_calendar(repo):
    assert repo.board("04040", date(2026, 12, 25), 0, 86400, "salidas") == []   # excepción tipo 2
    assert repo.board("18002", date(2026, 11, 12), 0, 86400, "salidas") == []   # 1014X solo el día 11
    assert len(repo.board("18002", D, 0, 86400, "salidas")) == 1


def test_first_departure(repo):
    r = repo.first_departure("03304", D)
    assert (r["source"], r["dep"], r["origen"]) == ("LD", 36000, "Madrid-Puerta de Atocha")
    assert repo.first_departure("19799", D)["source"] == "CER"
    assert repo.first_departure("99999", D) is None


def test_loaded_at(repo, tmp_path):
    from app.gtfs_static.repo import GtfsRepo
    assert repo.loaded_at() is not None
    assert GtfsRepo(tmp_path / "no.db").loaded_at() is None
```

- [ ] **Step 3: Ejecutar y ver que falla**

Run: `pytest tests/test_repo.py -v` → ERROR (`ModuleNotFoundError: app.gtfs_static.repo`)

- [ ] **Step 4: Implementación** — `app/gtfs_static/repo.py`

```python
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..geo import haversine_m
from .normalize import norm_text

# Servicio activo en la fecha :d (YYYYMMDD); :dow es 1 (lunes) … 7 (domingo). Requiere alias t = trips.
ACTIVE = """(
  (EXISTS(SELECT 1 FROM calendar c WHERE c.source=t.source AND c.service_id=t.service_id
          AND c.start_date<=:d AND c.end_date>=:d AND substr(c.days,:dow,1)='1')
   OR EXISTS(SELECT 1 FROM calendar_dates x WHERE x.source=t.source AND x.service_id=t.service_id
             AND x.date=:d AND x.exception_type=1))
  AND NOT EXISTS(SELECT 1 FROM calendar_dates x WHERE x.source=t.source AND x.service_id=t.service_id
                 AND x.date=:d AND x.exception_type=2))"""

_END_NAME = """(SELECT s.name FROM stop_times e JOIN stops s ON s.stop_id=e.stop_id
                WHERE e.source=t.source AND e.trip_id=t.trip_id ORDER BY e.seq {order} LIMIT 1)"""
_END_SEQ = "(SELECT {fn}(e.seq) FROM stop_times e WHERE e.source=t.source AND e.trip_id=t.trip_id)"


@dataclass(frozen=True)
class StopTime:
    stop_id: str
    name: str
    lat: float | None
    lon: float | None
    arr: int
    dep: int


@dataclass(frozen=True)
class TripInfo:
    source: str
    trip_id: str
    numero: str
    route_short: str
    route_long: str
    color: str
    shape_id: str
    stops: tuple[StopTime, ...]


def _day_params(d: date) -> dict:
    return {"d": d.strftime("%Y%m%d"), "dow": d.isoweekday()}


class GtfsRepo:
    """Consultas de solo lectura sobre gtfs.db. Abre una conexión corta por consulta."""

    def __init__(self, path: Path):
        self.path = path
        self._trips: dict[tuple[str, str], TripInfo | None] = {}
        self._stops: list[dict] | None = None

    def reload(self) -> None:
        self._trips.clear()
        self._stops = None

    def _con(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return closing(con)

    def loaded_at(self) -> str | None:
        if not self.path.exists():
            return None
        with self._con() as con:
            row = con.execute("SELECT value FROM meta WHERE key='loaded_at'").fetchone()
            return row["value"] if row else None

    def trip(self, source: str, trip_id: str) -> TripInfo | None:
        key = (source, trip_id)
        if key in self._trips:
            return self._trips[key]
        info = None
        with self._con() as con:
            row = con.execute(
                """SELECT t.numero, t.shape_id, r.short_name, r.long_name, r.color
                   FROM trips t LEFT JOIN routes r ON r.source=t.source AND r.route_id=t.route_id
                   WHERE t.source=? AND t.trip_id=?""", key).fetchone()
            if row:
                stops = tuple(StopTime(*s) for s in con.execute(
                    """SELECT st.stop_id, COALESCE(s.name, st.stop_id), s.lat, s.lon, st.arr, st.dep
                       FROM stop_times st LEFT JOIN stops s ON s.stop_id=st.stop_id
                       WHERE st.source=? AND st.trip_id=? ORDER BY st.seq""", key))
                info = TripInfo(source, trip_id, row["numero"] or "", row["short_name"] or "",
                                row["long_name"] or "", row["color"] or "", row["shape_id"] or "", stops)
        self._trips[key] = info
        return info

    def shape(self, shape_id: str) -> list[list[float]]:
        with self._con() as con:
            return [[r["lon"], r["lat"]] for r in con.execute(
                "SELECT lon, lat FROM shapes WHERE shape_id=? ORDER BY seq", (shape_id,))]

    def all_stops(self) -> list[dict]:
        if self._stops is None:
            with self._con() as con:
                self._stops = [dict(r) for r in con.execute(
                    "SELECT stop_id AS id, name AS nombre, lat, lon FROM stops")]
        return self._stops

    def stop(self, stop_id: str) -> dict | None:
        return next((s for s in self.all_stops() if s["id"] == stop_id), None)

    def search_stops(self, q: str, limit: int = 20) -> list[dict]:
        n = norm_text(q)
        with self._con() as con:
            return [dict(r) for r in con.execute(
                """SELECT stop_id AS id, name AS nombre, lat, lon FROM stops WHERE name_norm LIKE ?
                   ORDER BY (name_norm LIKE ?) DESC, length(name) LIMIT ?""",
                (f"%{n}%", f"{n}%", limit))]

    def near(self, lat: float, lon: float, limit: int = 10) -> list[dict]:
        ranked = sorted(
            ({**s, "dist_m": round(haversine_m(lat, lon, s["lat"], s["lon"]))} for s in self.all_stops()),
            key=lambda s: s["dist_m"])
        return ranked[:limit]

    def board(self, stop_id: str, d: date, t_from: int, t_to: int, tipo: str) -> list[dict]:
        """Pasos por una estación en la fecha de servicio d, entre t_from y t_to (segundos del día)."""
        col = "dep" if tipo == "salidas" else "arr"
        sql = f"""
            SELECT t.source, t.trip_id, t.numero, r.short_name AS route_short, st.arr, st.dep, st.seq,
                   {_END_NAME.format(order='ASC')} AS origen, {_END_NAME.format(order='DESC')} AS destino,
                   {_END_SEQ.format(fn='MIN')} AS first_seq, {_END_SEQ.format(fn='MAX')} AS last_seq
            FROM stop_times st
            JOIN trips t ON t.source=st.source AND t.trip_id=st.trip_id
            LEFT JOIN routes r ON r.source=t.source AND r.route_id=t.route_id
            WHERE st.stop_id=:stop AND st.{col} BETWEEN :a AND :b AND {ACTIVE}
            ORDER BY st.{col}"""
        with self._con() as con:
            rows = [dict(r) for r in con.execute(
                sql, {"stop": stop_id, "a": t_from, "b": t_to, **_day_params(d)})]
        edge = "last_seq" if tipo == "salidas" else "first_seq"
        return [r for r in rows if r["seq"] != r[edge]]

    def first_departure(self, numero: str, d: date) -> dict | None:
        """Primera salida del día de un tren por su número: source, trip_id, dep, origen."""
        sql = f"""
            SELECT t.source, t.trip_id, st.dep, COALESCE(s.name, st.stop_id) AS origen
            FROM trips t
            JOIN stop_times st ON st.source=t.source AND st.trip_id=t.trip_id
                 AND st.seq={_END_SEQ.format(fn='MIN')}
            LEFT JOIN stops s ON s.stop_id=st.stop_id
            WHERE t.numero=:n AND {ACTIVE}
            ORDER BY st.dep LIMIT 1"""
        with self._con() as con:
            row = con.execute(sql, {"n": numero, **_day_params(d)}).fetchone()
            return dict(row) if row else None
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `pytest tests/test_repo.py -v` → 8 passed

- [ ] **Step 6: Commit**

```bash
git add api/app/gtfs_static/repo.py api/tests/conftest.py api/tests/test_repo.py
git commit -m "feat(api): repositorio de consultas GTFS (viajes, estaciones, panel, calendario)"
```

---

### Task 5: Modelos de tiempo real

**Files:**
- Create: `api/app/realtime/models.py`
- Test: `api/tests/test_models.py`

- [ ] **Step 1: Test que falla** — `tests/test_models.py`

```python
from app.realtime.models import Snapshot, Train


def make_train(**kw) -> Train:
    base = dict(id="LD:03304", source="LD", trip_id="T", fecha="2026-11-11", numero="03304",
                servicio="AVE", linea=None, color="#FF0000", lat=41.0, lon=-2.0, rumbo=None,
                estado="IN_TRANSIT_TO", origen=None, destino=None, proxima_parada=None,
                retraso_min=None, anden=None, progreso=None, casado_con_horario=False,
                cancelado=False, ts=0, paradas=[], shape_id="")
    return Train(**{**base, **kw})


def test_light_has_only_map_fields():
    assert set(make_train().light()) == {
        "id", "numero", "servicio", "linea", "color", "lat", "lon", "rumbo", "retraso_min", "estado"}


def test_empty_snapshot_and_by_trip():
    assert Snapshot.empty().trains == {}
    snap = Snapshot({"LD:03304": make_train()}, 0.0, {}, "x")
    assert snap.by_trip[("LD", "T")].id == "LD:03304"
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_models.py -v` → FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implementación** — `app/realtime/models.py`

```python
from dataclasses import dataclass, field
from functools import cached_property

LIGHT_FIELDS = ("id", "numero", "servicio", "linea", "color", "lat", "lon", "rumbo", "retraso_min", "estado")


@dataclass
class Feed:
    """Un feed GTFS-RT ya decodificado: entidades con la forma del JSON de Renfe."""
    entities: list[dict]
    timestamp: int          # header.timestamp del feed
    fetched_at: float
    stale: bool = False     # True si la última descarga falló y este es un dato antiguo


@dataclass
class Train:
    id: str                 # "LD:03304" / "CER:35903"
    source: str             # "LD" | "CER"
    trip_id: str
    fecha: str              # fecha de servicio, YYYY-MM-DD
    numero: str
    servicio: str           # AVE, ALVIA, MD… o "CERCANIAS"
    linea: str | None       # C1, C5… solo Cercanías
    color: str              # "#RRGGBB"
    lat: float
    lon: float
    rumbo: int | None
    estado: str             # IN_TRANSIT_TO | INCOMING_AT | STOPPED_AT
    origen: str | None
    destino: str | None
    proxima_parada: dict | None   # {id, nombre, hora_prog, hora_est}
    retraso_min: int | None
    anden: str | None
    progreso: float | None
    casado_con_horario: bool
    cancelado: bool
    ts: int
    paradas: list[dict] = field(default_factory=list)
    # cada parada: {id, nombre, lat, lon, ts_prog, ts_est, hora_prog, hora_est, retraso_s,
    #               estado: pasada|proxima|pendiente|suprimida}
    shape_id: str = ""

    def light(self) -> dict:
        return {k: getattr(self, k) for k in LIGHT_FIELDS}


@dataclass
class Snapshot:
    trains: dict[str, Train]
    generated_at: float
    feeds: dict[str, dict]  # {"LD": {"edad_s": 12, "stale": False}, "CER": {...}}
    etag: str

    @classmethod
    def empty(cls) -> "Snapshot":
        return cls({}, 0.0, {}, "empty")

    @cached_property
    def by_trip(self) -> dict[tuple[str, str], Train]:
        return {(t.source, t.trip_id): t for t in self.trains.values()}
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_models.py -v` → 2 passed

- [ ] **Step 5: Commit**

```bash
git add api/app/realtime/models.py api/tests/test_models.py
git commit -m "feat(api): modelos Feed, Train y Snapshot"
```

---

### Task 6: `build_snapshot` (función pura)

**Files:**
- Create: `api/app/realtime/snapshot.py`
- Test: `api/tests/test_snapshot.py`

- [ ] **Step 1: Test que falla** — `tests/test_snapshot.py`

```python
import json
from pathlib import Path

from app.realtime.models import Feed
from app.realtime.snapshot import build_snapshot, parse_label
from tests.helpers import NOW

LD_TRIP = "0330412026-11-11"
FIX = Path(__file__).parent / "fixtures"


def vp(trip_id, lat, lon, stop_id=None, vid="03304", label="03304"):
    v = {"trip": {"tripId": trip_id}, "position": {"latitude": lat, "longitude": lon},
         "currentStatus": "IN_TRANSIT_TO", "vehicle": {"id": vid, "label": label}}
    if stop_id:
        v["stopId"] = stop_id
    return {"id": f"VP_{vid}", "vehicle": v}


def tu(trip_id, updates, rel="SCHEDULED"):
    return {"id": f"TU_{trip_id}", "tripUpdate": {
        "trip": {"tripId": trip_id, "scheduleRelationship": rel}, "stopTimeUpdate": updates}}


def feed(entities):
    return Feed(entities=entities, timestamp=int(NOW), fetched_at=NOW)


def test_parse_label():
    assert parse_label("C5-35903-PLATF.(3)") == ("C5", "35903", "3")
    assert parse_label("C1-23537") == ("C1", "23537", None)
    assert parse_label("03304") == (None, None, None)
    assert parse_label("") == (None, None, None)


def test_matched_ld_train_with_delay(repo):
    feeds = {
        "LD_vp": feed([vp(LD_TRIP, 41.0, -2.0, "04040")]),
        "LD_tu": feed([tu(LD_TRIP, [{"stopId": "04040", "arrival": {"delay": 300}}])]),
    }
    t = build_snapshot(feeds, repo, None, NOW).trains["LD:03304"]
    assert (t.servicio, t.numero, t.linea, t.color) == ("AVE", "03304", None, "#FF0000")
    assert (t.origen, t.destino) == ("Madrid-Puerta de Atocha", "Barcelona-Sants")
    assert t.proxima_parada == {"id": "04040", "nombre": "Zaragoza Delicias",
                                "hora_prog": "11:20", "hora_est": "11:25"}
    assert (t.retraso_min, t.progreso, t.casado_con_horario, t.fecha) == (5, 0.5, True, "2026-11-11")
    assert [p["estado"] for p in t.paradas] == ["pasada", "proxima", "pendiente"]
    assert t.paradas[0]["hora_est"] == "10:00"      # antes del primer retraso conocido
    assert t.paradas[2]["hora_est"] == "12:50"      # el retraso se propaga hacia delante


def test_unmatched_cercanias_uses_label(repo):
    feeds = {"CER_vp": feed([vp("3014X35903C5", 37.32, -5.96, "51103", vid="35903",
                                label="C5-35903-PLATF.(3)")])}
    t = build_snapshot(feeds, repo, None, NOW).trains["CER:35903"]
    assert (t.servicio, t.linea, t.numero, t.anden) == ("CERCANIAS", "C5", "35903", "3")
    assert (t.casado_con_horario, t.paradas, t.retraso_min, t.fecha) == (False, [], None, "2026-11-11")


def test_matched_cercanias(repo):
    feeds = {"CER_vp": feed([vp("1014X19799C1", 40.41, -3.70, vid="19799", label="C1-19799-PLATF.(2)")])}
    t = build_snapshot(feeds, repo, None, NOW).trains["CER:19799"]
    assert (t.linea, t.destino, t.anden, t.fecha, t.color) == (
        "C1", "Madrid-Atocha Cercanías", "2", "2026-11-11", "#75B6E0")
    assert t.shape_id == "10_C1"


def test_skipped_stop_and_cancelled_trip(repo):
    feeds = {
        "LD_vp": feed([vp(LD_TRIP, 41.0, -2.0)]),
        "LD_tu": feed([tu(LD_TRIP, [{"stopId": "04040", "scheduleRelationship": "SKIPPED"}], rel="CANCELED")]),
    }
    t = build_snapshot(feeds, repo, None, NOW).trains["LD:03304"]
    assert [p["estado"] for p in t.paradas] == ["pasada", "suprimida", "proxima"]
    assert t.cancelado is True
    assert t.proxima_parada["id"] == "71801"


def test_bearing_from_previous_snapshot(repo):
    s1 = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -2.0)])}, repo, None, NOW)
    assert s1.trains["LD:03304"].rumbo is None
    s2 = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -1.9)])}, repo, s1, NOW + 15)
    assert abs(s2.trains["LD:03304"].rumbo - 90) <= 1
    s3 = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -1.9)])}, repo, s2, NOW + 30)
    assert s3.trains["LD:03304"].rumbo == s2.trains["LD:03304"].rumbo   # parado: conserva el rumbo


def test_etag_and_feed_age(repo):
    a = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -2.0)])}, repo, None, NOW)
    b = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -2.0)])}, repo, None, NOW)
    c = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.5, -2.0)])}, repo, None, NOW)
    assert a.etag == b.etag != c.etag
    stale = Feed(entities=[], timestamp=int(NOW) - 3600, fetched_at=NOW, stale=True)
    s = build_snapshot({"LD_vp": stale}, repo, None, NOW)
    assert s.feeds["LD"] == {"edad_s": 3600, "stale": True}
    assert "CER" not in s.feeds


def test_real_fixtures_do_not_crash(repo):
    def load(name):
        d = json.loads((FIX / name).read_text(encoding="utf-8"))
        return Feed(entities=d["entity"], timestamp=int(d["header"]["timestamp"]), fetched_at=NOW)

    feeds = {"LD_vp": load("vehicle_positions_LD.json"), "LD_tu": load("trip_updates_LD.json"),
             "CER_vp": load("vehicle_positions.json"), "CER_tu": load("trip_updates.json")}
    snap = build_snapshot(feeds, repo, None, NOW)
    assert len(snap.trains) > 200
    assert all(-90 <= t.lat <= 90 for t in snap.trains.values())
    assert any(t.anden for t in snap.trains.values() if t.source == "CER")
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_snapshot.py -v` → FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implementación** — `app/realtime/snapshot.py`

```python
import hashlib
import json
import re
from datetime import date, timedelta

from ..geo import bearing, haversine_m
from ..gtfs_static.repo import GtfsRepo, TripInfo
from ..timeutil import hhmm, madrid_date, service_midnight
from .models import Feed, Snapshot, Train

LABEL_RE = re.compile(r"^(?P<linea>[^-]+)-(?P<num>\d+)(?:-PLATF\.\((?P<anden>[^)]+)\))?")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})$")
DEFAULT_COLOR = "#9AA0A6"
MIN_MOVE_M = 30


def parse_label(label: str) -> tuple[str | None, str | None, str | None]:
    """'C5-35903-PLATF.(3)' → ('C5', '35903', '3'). Si no tiene ese formato, todo None."""
    m = LABEL_RE.match(label or "")
    return (m["linea"], m["num"], m["anden"]) if m else (None, None, None)


def service_date(trip: TripInfo, trip_id: str, now: float) -> date:
    """LD lleva la fecha al final del trip_id. En Cercanías se elige hoy o ayer según el horario."""
    m = DATE_RE.search(trip_id)
    if m:
        return date.fromisoformat(m.group(1))
    today = madrid_date(now)
    for d in (today, today - timedelta(days=1)):
        base = service_midnight(d)
        if base + trip.stops[0].dep - 3600 <= now <= base + trip.stops[-1].arr + 3 * 3600:
            return d
    return today


def _delays(tu: dict | None) -> tuple[dict[str, int], set[str], bool, int | None]:
    """Retraso por parada (s), paradas suprimidas, viaje cancelado y retraso global del viaje."""
    if not tu:
        return {}, set(), False, None
    delays: dict[str, int] = {}
    skipped: set[str] = set()
    for stu in tu.get("stopTimeUpdate", []):
        event = stu.get("arrival") or stu.get("departure") or {}
        if "delay" in event:
            delays[stu.get("stopId")] = int(event["delay"])
        elif stu.get("scheduleRelationship") == "SKIPPED":
            skipped.add(stu.get("stopId"))
    cancelled = tu.get("trip", {}).get("scheduleRelationship") == "CANCELED"
    return delays, skipped - delays.keys(), cancelled, tu.get("delay")


def _next_index(paradas: list[dict], stop_id: str | None, now: float) -> int:
    live = [i for i, p in enumerate(paradas) if p["estado"] != "suprimida"] or list(range(len(paradas)))
    if stop_id:
        for i in live:
            if paradas[i]["id"] == stop_id:
                return i
    for i in live:
        if paradas[i]["ts_est"] >= now:
            return i
    return live[-1]


def _apply_schedule(train: Train, trip: TripInfo, v: dict, delays: dict[str, int],
                    skipped: set[str], base_delay: int | None, now: float) -> None:
    d = service_date(trip, trip.trip_id, now)
    base = service_midnight(d)
    cur = int(base_delay or 0)
    paradas = []
    for i, st in enumerate(trip.stops):
        if st.stop_id in delays:
            cur = delays[st.stop_id]
        ts_prog = base + (st.dep if i == 0 else st.arr)
        paradas.append({
            "id": st.stop_id, "nombre": st.name, "lat": st.lat, "lon": st.lon,
            "ts_prog": int(ts_prog), "ts_est": int(ts_prog + cur),
            "hora_prog": hhmm(ts_prog), "hora_est": hhmm(ts_prog + cur), "retraso_s": cur,
            "estado": "suprimida" if st.stop_id in skipped else "pendiente",
        })
    idx = _next_index(paradas, v.get("stopId"), now)
    for i, p in enumerate(paradas):
        if p["estado"] != "suprimida":
            p["estado"] = "pasada" if i < idx else "proxima" if i == idx else "pendiente"
    nxt = paradas[idx]
    train.fecha = d.isoformat()
    train.paradas = paradas
    train.origen, train.destino = paradas[0]["nombre"], paradas[-1]["nombre"]
    train.proxima_parada = {k: nxt[k] for k in ("id", "nombre", "hora_prog", "hora_est")}
    train.retraso_min = round(nxt["retraso_s"] / 60)
    train.progreso = round(idx / (len(paradas) - 1), 2) if len(paradas) > 1 else 0.0
    train.casado_con_horario = True
    train.shape_id = trip.shape_id
    if trip.numero:
        train.numero = trip.numero
    if trip.color:
        train.color = f"#{trip.color}"
    if train.source == "CER":
        train.linea = trip.route_short or train.linea
    else:
        train.servicio = trip.route_short


def _build_train(src: str, v: dict, tus: dict[str, dict], repo: GtfsRepo,
                 prev: Snapshot | None, now: float, feed_ts: int) -> Train:
    trip_id = v.get("trip", {}).get("tripId", "")
    veh = v.get("vehicle", {})
    vid = veh.get("id") or trip_id
    linea, num, anden = parse_label(veh.get("label", ""))
    tid = f"{src}:{vid}"
    lat, lon = v["position"]["latitude"], v["position"]["longitude"]
    old = prev.trains.get(tid) if prev else None
    rumbo = old.rumbo if old else None
    if old and haversine_m(old.lat, old.lon, lat, lon) > MIN_MOVE_M:
        rumbo = round(bearing(old.lat, old.lon, lat, lon))
    delays, skipped, cancelled, base_delay = _delays(tus.get(trip_id))
    train = Train(
        id=tid, source=src, trip_id=trip_id, fecha=madrid_date(now).isoformat(), numero=num or vid,
        servicio="CERCANIAS" if src == "CER" else "", linea=linea if src == "CER" else None,
        color=DEFAULT_COLOR, lat=lat, lon=lon, rumbo=rumbo,
        estado=v.get("currentStatus", "IN_TRANSIT_TO"), origen=None, destino=None, proxima_parada=None,
        retraso_min=round(base_delay / 60) if base_delay is not None else None, anden=anden,
        progreso=None, casado_con_horario=False, cancelado=cancelled,
        ts=int(v.get("timestamp", feed_ts)))
    trip = repo.trip(src, trip_id) if trip_id else None
    if trip and trip.stops:
        _apply_schedule(train, trip, v, delays, skipped, base_delay, now)
    return train


def build_snapshot(feeds: dict[str, Feed], repo: GtfsRepo, prev: Snapshot | None, now: float) -> Snapshot:
    """Cruza los feeds en vivo con los horarios. No hace E/S de red; solo lee del repo."""
    trains: dict[str, Train] = {}
    info: dict[str, dict] = {}
    for src in ("LD", "CER"):
        vp = feeds.get(f"{src}_vp")
        if not vp:
            continue
        info[src] = {"edad_s": max(0, int(now - vp.timestamp)), "stale": vp.stale}
        tu_feed = feeds.get(f"{src}_tu")
        tus = {e["tripUpdate"].get("trip", {}).get("tripId"): e["tripUpdate"]
               for e in (tu_feed.entities if tu_feed else []) if "tripUpdate" in e}
        for e in vp.entities:
            v = e.get("vehicle")
            if v and "position" in v:
                t = _build_train(src, v, tus, repo, prev, now, vp.timestamp)
                trains[t.id] = t
    payload = json.dumps([trains[k].light() for k in sorted(trains)], sort_keys=True)
    return Snapshot(trains, now, info, hashlib.sha1(payload.encode()).hexdigest())
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_snapshot.py -v` → 8 passed

- [ ] **Step 5: Commit**

```bash
git add api/app/realtime/snapshot.py api/tests/test_snapshot.py
git commit -m "feat(api): build_snapshot cruza posiciones, retrasos y horarios"
```

**Corrección tras revisar los feeds reales (Task 6b)**

- **Elección de variante.** En LD el mismo vehículo (`vehicle.id`) llega una vez por variante de recorrido. Las entidades se agrupan por `f"{src}:{vid}"` y el tren se construye con una sola, la mejor según `_rank`: (viaje en el repo y `stopId` entre sus paradas, viaje en el repo, n.º de paradas, índice del `stopId` en el viaje). A igualdad gana la primera del feed.
- **Fusión de tripUpdates.** `tus` guarda la lista de `tripUpdate` de cada `tripId`. Retrasos por parada, paradas `SKIPPED` y `delay` global salen solo de las entidades no `CANCELED` (la posterior sobrescribe a la anterior). Una parada `SKIPPED` cuenta como suprimida aunque otra entrada le dé retraso, y ese retraso se sigue usando para las horas.
- **`cancelado`.** Solo es True si hay una entidad `CANCELED` y además (a) el viaje casa con horario y todas sus paradas están suprimidas, o (b) ninguna entidad no cancelada trae `stopTimeUpdate`. Con supresión parcial es False y las paradas afectadas quedan con `estado == "suprimida"`. Si todas están suprimidas, `_next_index` usa su respaldo y `proxima_parada`, `retraso_min` y `progreso` se siguen calculando.

---

### Task 7: Descarga y decodificación de feeds `.pb`

**Files:**
- Create: `api/app/realtime/fetch.py`
- Test: `api/tests/test_fetch.py`

- [ ] **Step 1: Test que falla** — `tests/test_fetch.py`

```python
import asyncio

import httpx
from google.transit import gtfs_realtime_pb2

from app.realtime.fetch import FeedFetcher, decode_feed


def sample_pb() -> bytes:
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = 1794392678
    e = msg.entity.add()
    e.id = "VP_C5-35903"
    e.vehicle.trip.trip_id = "3014X35903C5"
    e.vehicle.position.latitude = 37.5
    e.vehicle.position.longitude = -5.9
    e.vehicle.current_status = gtfs_realtime_pb2.VehiclePosition.INCOMING_AT
    e.vehicle.stop_id = "51103"
    e.vehicle.vehicle.id = "35903"
    e.vehicle.vehicle.label = "C5-35903-PLATF.(3)"
    return msg.SerializeToString()


def test_decode_feed_matches_renfe_json_shape():
    f = decode_feed(sample_pb(), fetched_at=10.0)
    v = f.entities[0]["vehicle"]
    assert (f.timestamp, f.fetched_at, f.stale) == (1794392678, 10.0, False)
    assert v["trip"]["tripId"] == "3014X35903C5"
    assert v["currentStatus"] == "INCOMING_AT"
    assert v["stopId"] == "51103"
    assert v["vehicle"]["label"] == "C5-35903-PLATF.(3)"
    assert abs(v["position"]["latitude"] - 37.5) < 1e-6


def test_fetcher_keeps_last_good_feed_and_backs_off():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=sample_pb()) if calls["n"] == 1 else httpx.Response(500)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = FeedFetcher({"CER_vp": "https://example.test/vp.pb"}, client)
            first = await fetcher.fetch_all(now=100.0)
            second = await fetcher.fetch_all(now=115.0)   # falla: conserva el anterior, marcado stale
            third = await fetcher.fetch_all(now=120.0)    # dentro de la espera: no hace petición
            return first, second, third

    first, second, third = asyncio.run(run())
    assert first["CER_vp"].stale is False
    assert second["CER_vp"].stale is True and len(second["CER_vp"].entities) == 1
    assert third["CER_vp"].stale is True
    assert calls["n"] == 2


def test_fetcher_without_any_success_returns_no_feed():
    async def run():
        transport = httpx.MockTransport(lambda r: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            return await FeedFetcher({"LD_vp": "https://example.test/x.pb"}, client).fetch_all(now=1.0)

    assert asyncio.run(run()) == {}
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_fetch.py -v` → FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implementación** — `app/realtime/fetch.py`

```python
import asyncio
import logging
from dataclasses import replace

import httpx
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2

from .models import Feed

log = logging.getLogger(__name__)
MAX_BACKOFF_S = 120


def decode_feed(raw: bytes, fetched_at: float) -> Feed:
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(raw)
    d = MessageToDict(msg)
    return Feed(entities=d.get("entity", []), timestamp=int(d.get("header", {}).get("timestamp", 0)),
                fetched_at=fetched_at)


class FeedFetcher:
    """Descarga los feeds. Si uno falla conserva el último bueno (stale) y espera antes de reintentar."""

    def __init__(self, urls: dict[str, str], client: httpx.AsyncClient):
        self.urls = urls
        self.client = client
        self.last: dict[str, Feed] = {}
        self.fails: dict[str, int] = {}
        self.next_try: dict[str, float] = {}

    async def fetch_all(self, now: float) -> dict[str, Feed]:
        await asyncio.gather(*(self._one(key, url, now) for key, url in self.urls.items()))
        return dict(self.last)

    async def _one(self, key: str, url: str, now: float) -> None:
        if now < self.next_try.get(key, 0.0):
            return
        try:
            resp = await self.client.get(url, timeout=10)
            resp.raise_for_status()
            self.last[key] = decode_feed(resp.content, now)
            self.fails[key] = 0
        except Exception as exc:  # red, HTTP o protobuf corrupto: mismo tratamiento
            n = self.fails.get(key, 0) + 1
            self.fails[key] = n
            self.next_try[key] = now + min(MAX_BACKOFF_S, 15 * 2 ** (n - 1))
            log.warning("feed %s falló (%s); reintento en %ss", key, exc, int(self.next_try[key] - now))
            if key in self.last:
                self.last[key] = replace(self.last[key], stale=True)
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_fetch.py -v` → 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/app/realtime/fetch.py api/tests/test_fetch.py
git commit -m "feat(api): descarga de feeds GTFS-RT con último dato bueno y espera exponencial"
```

---

### Task 8: Base de datos de la app (favoritos, suscripciones, avisos enviados)

**Files:**
- Create: `api/app/appdb.py`
- Test: `api/tests/test_appdb.py`

- [ ] **Step 1: Test que falla** — `tests/test_appdb.py`

```python
import pytest

from app import appdb

AVISOS = {"retraso": True, "cancelacion": True, "anden": False, "salida": True}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "app.db"
    appdb.init(path)
    appdb.init(path)   # idempotente
    return path


def test_favorites_crud(db):
    appdb.put_favorite(db, "dev-1", "tren", "03304", AVISOS)
    appdb.put_favorite(db, "dev-1", "estacion", "04040", {})
    appdb.put_favorite(db, "dev-2", "tren", "03304", AVISOS)
    appdb.put_favorite(db, "dev-1", "tren", "03304", {**AVISOS, "anden": True})   # actualiza
    mine = appdb.list_favorites(db, "dev-1")
    assert {(f["tipo"], f["ref"]) for f in mine} == {("tren", "03304"), ("estacion", "04040")}
    assert next(f for f in mine if f["tipo"] == "tren")["avisos"]["anden"] is True
    assert len(appdb.list_favorites(db)) == 3
    appdb.delete_favorite(db, "dev-1", "tren", "03304")
    assert [f["tipo"] for f in appdb.list_favorites(db, "dev-1")] == ["estacion"]


def test_subscriptions(db):
    sub = {"endpoint": "https://push.example.test/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert appdb.get_subscription(db, "dev-1") is None
    appdb.put_subscription(db, "dev-1", sub)
    assert appdb.get_subscription(db, "dev-1") == sub
    appdb.delete_subscription(db, "dev-1")
    assert appdb.get_subscription(db, "dev-1") is None


def test_notified(db):
    appdb.set_notified(db, "dev-1", "03304", "2026-11-11", "retraso", "5")
    appdb.set_notified(db, "dev-1", "03304", "2026-11-11", "retraso", "10")
    assert appdb.notified_map(db) == {("dev-1", "03304", "2026-11-11", "retraso"): "10"}
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_appdb.py -v` → FAIL (`ImportError: cannot import name 'appdb'`)

- [ ] **Step 3: Implementación** — `app/appdb.py`

```python
import json
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites(device_id TEXT, tipo TEXT, ref TEXT, avisos TEXT,
                                     PRIMARY KEY(device_id, tipo, ref));
CREATE TABLE IF NOT EXISTS push_subs(device_id TEXT PRIMARY KEY, sub TEXT);
CREATE TABLE IF NOT EXISTS notified(device_id TEXT, ref TEXT, fecha TEXT, tipo TEXT, valor TEXT,
                                    PRIMARY KEY(device_id, ref, fecha, tipo));
"""


def _run(path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    with closing(sqlite3.connect(path)) as con, con:   # 'con' como contexto hace commit
        return con.execute(sql, params).fetchall()


def init(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as con, con:
        con.executescript(SCHEMA)


def list_favorites(path: Path, device_id: str | None = None) -> list[dict]:
    sql, params = "SELECT device_id, tipo, ref, avisos FROM favorites", ()
    if device_id is not None:
        sql, params = sql + " WHERE device_id=?", (device_id,)
    return [{"device_id": d, "tipo": t, "ref": r, "avisos": json.loads(a)} for d, t, r, a in _run(path, sql, params)]


def put_favorite(path: Path, device_id: str, tipo: str, ref: str, avisos: dict) -> None:
    _run(path, "INSERT OR REPLACE INTO favorites VALUES(?,?,?,?)", (device_id, tipo, ref, json.dumps(avisos)))


def delete_favorite(path: Path, device_id: str, tipo: str, ref: str) -> None:
    _run(path, "DELETE FROM favorites WHERE device_id=? AND tipo=? AND ref=?", (device_id, tipo, ref))


def put_subscription(path: Path, device_id: str, sub: dict) -> None:
    _run(path, "INSERT OR REPLACE INTO push_subs VALUES(?,?)", (device_id, json.dumps(sub)))


def get_subscription(path: Path, device_id: str) -> dict | None:
    rows = _run(path, "SELECT sub FROM push_subs WHERE device_id=?", (device_id,))
    return json.loads(rows[0][0]) if rows else None


def delete_subscription(path: Path, device_id: str) -> None:
    _run(path, "DELETE FROM push_subs WHERE device_id=?", (device_id,))


def notified_map(path: Path) -> dict[tuple[str, str, str, str], str]:
    return {(d, r, f, t): v for d, r, f, t, v in
            _run(path, "SELECT device_id, ref, fecha, tipo, valor FROM notified")}


def set_notified(path: Path, device_id: str, ref: str, fecha: str, tipo: str, valor: str) -> None:
    _run(path, "INSERT OR REPLACE INTO notified VALUES(?,?,?,?,?)", (device_id, ref, fecha, tipo, valor))
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_appdb.py -v` → 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/app/appdb.py api/tests/test_appdb.py
git commit -m "feat(api): almacenamiento de favoritos, suscripciones push y avisos enviados"
```

---

### Task 9: App FastAPI — `/health`, `/trains`, `/trains/{id}`, `/search`

**Files:**
- Create: `api/app/state.py`, `api/app/main.py`, `api/app/api/trains.py`
- Modify: `api/tests/conftest.py` (añadir fixture `client`)
- Test: `api/tests/test_api_trains.py`

- [ ] **Step 1: Añadir fixture `client`** — al final de `tests/conftest.py`

```python
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.realtime.models import Feed
from app.realtime.snapshot import build_snapshot
from tests.helpers import NOW

LD_TRIP = "0330412026-11-11"


def sample_feeds() -> dict[str, Feed]:
    """Un AVE con 5 min de retraso camino de Zaragoza y un Cercanías sin casar."""
    def feed(entities):
        return Feed(entities=entities, timestamp=int(NOW), fetched_at=NOW)

    return {
        "LD_vp": feed([{"id": "VP_03304", "vehicle": {
            "trip": {"tripId": LD_TRIP}, "position": {"latitude": 41.0, "longitude": -2.0},
            "currentStatus": "IN_TRANSIT_TO", "stopId": "04040",
            "vehicle": {"id": "03304", "label": "03304"}}}]),
        "LD_tu": feed([{"id": "TU", "tripUpdate": {
            "trip": {"tripId": LD_TRIP},
            "stopTimeUpdate": [{"stopId": "04040", "arrival": {"delay": 300}}]}}]),
        "CER_vp": feed([{"id": "VP_C5", "vehicle": {
            "trip": {"tripId": "3014X35903C5"}, "position": {"latitude": 37.32, "longitude": -5.96},
            "currentStatus": "INCOMING_AT", "stopId": "51103",
            "vehicle": {"id": "35903", "label": "C5-35903-PLATF.(3)"}}}]),
    }


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path)
    build_gtfs_db(settings.gtfs_db, gtfs_sources())
    app = create_app(settings, background=False)
    st = app.state.st
    st.clock = lambda: NOW
    st.snapshot = build_snapshot(sample_feeds(), st.repo, None, NOW)
    return TestClient(app)
```

- [ ] **Step 2: Test que falla** — `tests/test_api_trains.py`

```python
def test_health(client):
    body = client.get("/api/health").json()
    assert body["trenes"] == 2
    assert body["feeds"]["LD"] == {"edad_s": 0, "stale": False}
    assert body["gtfs_cargado"] is not None


def test_trains_list_is_light_and_has_etag(client):
    r = client.get("/api/trains")
    assert r.status_code == 200
    body = r.json()
    assert {t["id"] for t in body["trenes"]} == {"LD:03304", "CER:35903"}
    assert "paradas" not in body["trenes"][0]
    assert set(body["feeds"]) == {"LD", "CER"}
    etag = r.headers["etag"]
    again = client.get("/api/trains", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""


def test_train_detail(client):
    t = client.get("/api/trains/LD:03304").json()
    assert (t["servicio"], t["destino"], t["retraso_min"]) == ("AVE", "Barcelona-Sants", 5)
    assert [p["estado"] for p in t["paradas"]] == ["pasada", "proxima", "pendiente"]
    assert t["shape"] == [[-3.6902, 40.4066], [-0.9113, 41.6587], [2.14, 41.379]]   # sin shape: paradas
    assert client.get("/api/trains/LD:99999").status_code == 404


def test_unmatched_train_detail_has_empty_shape(client):
    t = client.get("/api/trains/CER:35903").json()
    assert (t["linea"], t["anden"], t["paradas"], t["shape"]) == ("C5", "3", [], [])


def test_search(client):
    by_number = client.get("/api/search", params={"q": "033"}).json()
    assert [t["id"] for t in by_number["trenes"]] == ["LD:03304"]
    assert by_number["estaciones"] == []
    by_name = client.get("/api/search", params={"q": "zarag"}).json()
    assert [s["id"] for s in by_name["estaciones"]] == ["04040"]
    assert by_name["trenes"] == []
    assert client.get("/api/search", params={"q": "z"}).json() == {"trenes": [], "estaciones": []}
```

- [ ] **Step 3: Ejecutar y ver que falla**

Run: `pytest tests/test_api_trains.py -v` → ERROR (`ModuleNotFoundError: app.main`)

- [ ] **Step 4: Implementación**

`app/state.py`:
```python
import time
from collections.abc import Callable

from .config import Settings
from .gtfs_static.repo import GtfsRepo
from .realtime.models import Snapshot


class State:
    """Estado compartido del proceso: repositorio GTFS, snapshot actual y anterior, reloj."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = GtfsRepo(settings.gtfs_db)
        self.app_db = settings.app_db
        self.snapshot: Snapshot = Snapshot.empty()
        self.prev: Snapshot | None = None
        self.clock: Callable[[], float] = time.time
```

`app/api/trains.py`:
```python
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request):
    st = request.app.state.st
    return {"trenes": len(st.snapshot.trains), "feeds": st.snapshot.feeds,
            "generado": st.snapshot.generated_at, "gtfs_cargado": st.repo.loaded_at()}


@router.get("/trains")
def trains(request: Request, response: Response):
    snap = request.app.state.st.snapshot
    etag = f'"{snap.etag}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return {"trenes": [t.light() for t in snap.trains.values()], "feeds": snap.feeds,
            "generado": snap.generated_at}


@router.get("/trains/{train_id}")
def train_detail(train_id: str, request: Request):
    st = request.app.state.st
    train = st.snapshot.trains.get(train_id)
    if not train:
        raise HTTPException(404, "Tren no encontrado")
    shape = st.repo.shape(train.shape_id) if train.shape_id else []
    if not shape:
        shape = [[p["lon"], p["lat"]] for p in train.paradas if p["lat"] is not None]
    return {**asdict(train), "shape": shape}


@router.get("/search")
def search(q: str, request: Request):
    st = request.app.state.st
    q = q.strip()
    if len(q) < 2:
        return {"trenes": [], "estaciones": []}
    if q.isdigit():
        hits = [t.light() for t in st.snapshot.trains.values() if q in t.numero]
        return {"trenes": hits[:20], "estaciones": []}
    return {"trenes": [], "estaciones": st.repo.search_stops(q)}
```

`app/main.py`:
```python
from fastapi import FastAPI

from . import appdb
from .api import trains
from .config import Settings
from .state import State


def create_app(settings: Settings | None = None, background: bool = True) -> FastAPI:
    settings = settings or Settings()
    appdb.init(settings.app_db)
    app = FastAPI(title="TrainRadar24h API")
    app.state.st = State(settings)
    app.state.background = background
    app.include_router(trains.router)
    return app
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `pytest tests/test_api_trains.py -v` → 5 passed

- [ ] **Step 6: Commit**

```bash
git add api/app/state.py api/app/main.py api/app/api/trains.py api/tests/conftest.py api/tests/test_api_trains.py
git commit -m "feat(api): endpoints de salud, lista de trenes con ETag, ficha y búsqueda"
```

---

### Task 10: Estaciones — cercanas y panel de salidas/llegadas

**Files:**
- Create: `api/app/api/stations.py`
- Modify: `api/app/main.py` (registrar router)
- Test: `api/tests/test_api_stations.py`

- [ ] **Step 1: Test que falla** — `tests/test_api_stations.py`

```python
def test_near(client):
    body = client.get("/api/stations/near", params={"lat": 41.6587, "lon": -0.9113}).json()
    assert body[0]["id"] == "04040" and body[0]["dist_m"] == 0


def test_departures_board_applies_live_delay(client):
    body = client.get("/api/stations/04040/board", params={"tipo": "salidas"}).json()
    assert body["estacion"]["nombre"] == "Zaragoza Delicias"
    row = body["filas"][0]
    assert (row["hora_prog"], row["hora_est"], row["retraso_min"]) == ("11:22", "11:27", 5)
    assert (row["destino"], row["servicio"], row["numero"]) == ("Barcelona-Sants", "AVE", "03304")
    assert (row["train_id"], row["estado"], row["anden"]) == ("LD:03304", "en_circulacion", None)


def test_arrivals_board(client):
    body = client.get("/api/stations/71801/board", params={"tipo": "llegadas"}).json()
    row = body["filas"][0]
    assert (row["hora_prog"], row["hora_est"], row["origen"]) == ("12:45", "12:50", "Madrid-Puerta de Atocha")


def test_board_outside_window_is_empty(client):
    # El Cercanías salió de Príncipe Pío a las 10:00; son las 11:00 y la ventana empieza a las 10:30.
    assert client.get("/api/stations/18002/board", params={"tipo": "salidas"}).json()["filas"] == []


def test_board_without_live_train_is_scheduled(client):
    client.app.state.st.snapshot.trains.clear()
    client.app.state.st.snapshot.__dict__.pop("by_trip", None)
    row = client.get("/api/stations/04040/board", params={"tipo": "salidas"}).json()["filas"][0]
    assert (row["hora_est"], row["retraso_min"], row["train_id"], row["estado"]) == (
        "11:22", None, None, "programado")


def test_board_errors(client):
    assert client.get("/api/stations/00000/board", params={"tipo": "salidas"}).status_code == 404
    assert client.get("/api/stations/04040/board", params={"tipo": "otra"}).status_code == 422
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_api_stations.py -v` → FAIL (404 en todas las rutas)

- [ ] **Step 3: Implementación** — `app/api/stations.py`

```python
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from ..timeutil import hhmm, madrid_date, service_midnight

router = APIRouter(prefix="/api/stations")
WINDOW_BEFORE_S = 30 * 60
WINDOW_AFTER_S = 3 * 3600


@router.get("/near")
def near(lat: float, lon: float, request: Request):
    return request.app.state.st.repo.near(lat, lon)


def _row(r: dict, tipo: str, base: float, fecha: str, stop_id: str, snap) -> dict:
    ts_prog = base + r["dep" if tipo == "salidas" else "arr"]
    train = snap.by_trip.get((r["source"], r["trip_id"]))
    if train and train.fecha != fecha:
        train = None    # mismo trip_id de Cercanías, pero de otro día
    parada = next((p for p in train.paradas if p["id"] == stop_id), None) if train else None
    delay = parada["retraso_s"] if parada else None
    if train and train.cancelado:
        estado = "cancelado"
    elif parada and parada["estado"] == "suprimida":
        estado = "suprimida"
    else:
        estado = "en_circulacion" if train else "programado"
    at_this_stop = bool(train and train.proxima_parada and train.proxima_parada["id"] == stop_id)
    return {
        "ts_prog": int(ts_prog), "hora_prog": hhmm(ts_prog), "hora_est": hhmm(ts_prog + (delay or 0)),
        "retraso_min": round(delay / 60) if delay is not None else None,
        "origen": r["origen"], "destino": r["destino"],
        "servicio": "CERCANIAS" if r["source"] == "CER" else r["route_short"],
        "linea": r["route_short"] if r["source"] == "CER" else None,
        "numero": r["numero"], "anden": train.anden if at_this_stop else None,
        "estado": estado, "train_id": train.id if train else None,
    }


@router.get("/{stop_id}/board")
def board(stop_id: str, request: Request, tipo: Literal["salidas", "llegadas"] = "salidas"):
    st = request.app.state.st
    stop = st.repo.stop(stop_id)
    if not stop:
        raise HTTPException(404, "Estación no encontrada")
    now = st.clock()
    today = madrid_date(now)
    filas = []
    # Hoy y ayer: un servicio de ayer con horas ≥ 24:00 sigue circulando de madrugada.
    for d in (today, today - timedelta(days=1)):
        base = service_midnight(d)
        t_from, t_to = int(now - WINDOW_BEFORE_S - base), int(now + WINDOW_AFTER_S - base)
        for r in st.repo.board(stop_id, d, t_from, t_to, tipo):
            filas.append(_row(r, tipo, base, d.isoformat(), stop_id, st.snapshot))
    filas.sort(key=lambda f: f["ts_prog"])
    return {"estacion": stop, "tipo": tipo, "filas": filas}
```

Modificar `app/main.py`: cambiar el import y registrar el router.
```python
from .api import stations, trains
```
```python
    app.include_router(trains.router)
    app.include_router(stations.router)
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_api_stations.py -v` → 6 passed

- [ ] **Step 5: Commit**

```bash
git add api/app/api/stations.py api/app/main.py api/tests/test_api_stations.py
git commit -m "feat(api): estaciones cercanas y panel de salidas y llegadas con retraso en vivo"
```

---

### Task 11: Favoritos y suscripción push (HTTP)

**Files:**
- Create: `api/app/api/user.py`
- Modify: `api/app/main.py` (registrar router)
- Test: `api/tests/test_api_user.py`

- [ ] **Step 1: Test que falla** — `tests/test_api_user.py`

```python
H = {"X-Device-Id": "device-0001"}


def test_device_id_is_required(client):
    assert client.get("/api/favorites").status_code == 422
    assert client.get("/api/favorites", headers={"X-Device-Id": "x"}).status_code == 422


def test_favorites_roundtrip(client):
    r = client.put("/api/favorites", headers=H, json={"tipo": "tren", "ref": "03304"})
    assert r.status_code == 200
    favs = client.get("/api/favorites", headers=H).json()
    assert favs == [{"tipo": "tren", "ref": "03304",
                     "avisos": {"retraso": True, "cancelacion": True, "anden": True, "salida": True}}]
    client.put("/api/favorites", headers=H,
               json={"tipo": "tren", "ref": "03304", "avisos": {"retraso": False}})
    assert client.get("/api/favorites", headers=H).json()[0]["avisos"]["retraso"] is False
    assert client.get("/api/favorites", headers={"X-Device-Id": "device-0002"}).json() == []
    client.delete("/api/favorites", headers=H, params={"tipo": "tren", "ref": "03304"})
    assert client.get("/api/favorites", headers=H).json() == []


def test_favorite_validation(client):
    assert client.put("/api/favorites", headers=H, json={"tipo": "avion", "ref": "1"}).status_code == 422


def test_push_subscription(client):
    client.app.state.st.settings.vapid_public_key = "BPublicKey"
    assert client.get("/api/push/vapid-public-key").json() == {"key": "BPublicKey"}
    sub = {"endpoint": "https://push.example.test/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert client.post("/api/push/subscription", headers=H, json=sub).status_code == 200
    from app import appdb
    assert appdb.get_subscription(client.app.state.st.app_db, "device-0001") == sub
    assert client.delete("/api/push/subscription", headers=H).status_code == 200
    assert appdb.get_subscription(client.app.state.st.app_db, "device-0001") is None
    assert client.post("/api/push/subscription", headers=H, json={"keys": {}}).status_code == 422
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_api_user.py -v` → FAIL (404)

- [ ] **Step 3: Implementación** — `app/api/user.py`

```python
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from .. import appdb

router = APIRouter(prefix="/api")
DeviceId = Annotated[str, Header(alias="X-Device-Id", min_length=8, max_length=64)]
DEFAULT_AVISOS = {"retraso": True, "cancelacion": True, "anden": True, "salida": True}


class FavoriteIn(BaseModel):
    tipo: Literal["tren", "estacion"]
    ref: str = Field(min_length=1, max_length=32)
    avisos: dict[str, bool] = {}


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10)
    keys: dict[str, str]


@router.get("/favorites")
def list_favorites(request: Request, device_id: DeviceId):
    favs = appdb.list_favorites(request.app.state.st.app_db, device_id)
    return [{"tipo": f["tipo"], "ref": f["ref"], "avisos": f["avisos"]} for f in favs]


@router.put("/favorites")
def put_favorite(fav: FavoriteIn, request: Request, device_id: DeviceId):
    avisos = {**DEFAULT_AVISOS, **{k: v for k, v in fav.avisos.items() if k in DEFAULT_AVISOS}}
    appdb.put_favorite(request.app.state.st.app_db, device_id, fav.tipo, fav.ref, avisos)
    return {"ok": True}


@router.delete("/favorites")
def delete_favorite(tipo: Literal["tren", "estacion"], ref: str, request: Request, device_id: DeviceId):
    appdb.delete_favorite(request.app.state.st.app_db, device_id, tipo, ref)
    return {"ok": True}


@router.get("/push/vapid-public-key")
def vapid_public_key(request: Request):
    return {"key": request.app.state.st.settings.vapid_public_key}


@router.post("/push/subscription")
def subscribe(sub: SubscriptionIn, request: Request, device_id: DeviceId):
    appdb.put_subscription(request.app.state.st.app_db, device_id, sub.model_dump())
    return {"ok": True}


@router.delete("/push/subscription")
def unsubscribe(request: Request, device_id: DeviceId):
    appdb.delete_subscription(request.app.state.st.app_db, device_id)
    return {"ok": True}
```

Modificar `app/main.py`:
```python
from .api import stations, trains, user
```
```python
    app.include_router(stations.router)
    app.include_router(user.router)
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_api_user.py -v` → 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/app/api/user.py api/app/main.py api/tests/test_api_user.py
git commit -m "feat(api): favoritos y suscripción push por dispositivo"
```

---

### Task 12: Lógica de avisos (`diff`, función pura)

**Files:**
- Create: `api/app/alerts/diff.py`
- Test: `api/tests/test_alerts_diff.py`

- [ ] **Step 1: Test que falla** — `tests/test_alerts_diff.py`

```python
from app.alerts.diff import diff
from app.realtime.models import Snapshot
from tests.helpers import NOW
from tests.test_models import make_train

ALL = {"retraso": True, "cancelacion": True, "anden": True, "salida": True}
FAV = [{"device_id": "dev-1", "tipo": "tren", "ref": "03304", "avisos": ALL}]
PROX = {"id": "04040", "nombre": "Zaragoza Delicias", "hora_prog": "11:20", "hora_est": "11:32"}


def snap(**kw) -> Snapshot:
    t = make_train(**kw)
    return Snapshot({t.id: t}, NOW, {}, "e")


def kinds(alerts):
    return [(a.tipo, a.valor) for a in alerts]


def test_delay_alert_uses_5_minute_buckets():
    cur = snap(retraso_min=12, proxima_parada=PROX)
    a = diff(None, cur, FAV, {}, {}, NOW)
    assert kinds(a) == [("retraso", "10")]
    assert a[0].titulo == "AVE 03304: +12 min"
    assert "Zaragoza Delicias" in a[0].cuerpo and "11:32" in a[0].cuerpo
    assert (a[0].device_id, a[0].ref, a[0].fecha, a[0].train_id) == ("dev-1", "03304", "2026-11-11", "LD:03304")
    seen = {("dev-1", "03304", "2026-11-11", "retraso"): "10"}
    assert diff(None, cur, FAV, seen, {}, NOW) == []                              # mismo tramo: no repite
    assert kinds(diff(None, snap(retraso_min=16), FAV, seen, {}, NOW)) == [("retraso", "15")]


def test_no_delay_alert_below_5_minutes_or_when_disabled():
    assert diff(None, snap(retraso_min=4), FAV, {}, {}, NOW) == []
    off = [{**FAV[0], "avisos": {**ALL, "retraso": False}}]
    assert diff(None, snap(retraso_min=30), off, {}, {}, NOW) == []


def test_cancellation_and_skipped_stops():
    assert kinds(diff(None, snap(cancelado=True), FAV, {}, {}, NOW)) == [("cancelacion", "cancelado")]
    sup = snap(paradas=[{"estado": "suprimida", "nombre": "Zaragoza Delicias"}, {"estado": "proxima", "nombre": "X"}])
    a = diff(None, sup, FAV, {}, {}, NOW)
    assert kinds(a) == [("cancelacion", "sup:1")] and "Zaragoza Delicias" in a[0].cuerpo
    seen = {("dev-1", "03304", "2026-11-11", "cancelacion"): "sup:1"}
    assert diff(None, sup, FAV, seen, {}, NOW) == []


def test_platform_change_needs_a_previous_platform():
    assert diff(None, snap(anden="3"), FAV, {}, {}, NOW) == []                    # primera vez: sin aviso
    assert diff(snap(anden="3"), snap(anden="3"), FAV, {}, {}, NOW) == []
    a = diff(snap(anden="3"), snap(anden="5"), FAV, {}, {}, NOW)
    assert kinds(a) == [("anden", "5")]


def test_departure_alert_15_minutes_before():
    empty = Snapshot.empty()
    dep = {"03304": {"ts": NOW + 600, "origen": "Madrid-Puerta de Atocha", "fecha": "2026-11-11"}}
    a = diff(None, empty, FAV, {}, dep, NOW)
    assert kinds(a) == [("salida", "1")] and "Madrid-Puerta de Atocha" in a[0].cuerpo
    assert diff(None, empty, FAV, {}, {"03304": {**dep["03304"], "ts": NOW + 1200}}, NOW) == []   # falta mucho
    assert diff(None, empty, FAV, {}, {"03304": {**dep["03304"], "ts": NOW - 60}}, NOW) == []     # ya salió
    assert diff(None, empty, FAV, {("dev-1", "03304", "2026-11-11", "salida"): "1"}, dep, NOW) == []


def test_station_favorites_and_unknown_trains_are_ignored():
    favs = [{"device_id": "dev-1", "tipo": "estacion", "ref": "04040", "avisos": ALL},
            {"device_id": "dev-1", "tipo": "tren", "ref": "99999", "avisos": ALL}]
    assert diff(None, snap(retraso_min=30), favs, {}, {}, NOW) == []
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_alerts_diff.py -v` → FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implementación** — `app/alerts/diff.py`

```python
from dataclasses import dataclass

from ..realtime.models import Snapshot, Train
from ..timeutil import hhmm

DELAY_STEP_MIN = 5
DEPARTURE_WINDOW_S = 15 * 60


@dataclass(frozen=True)
class Alert:
    device_id: str
    ref: str            # número de tren del favorito
    fecha: str          # fecha de servicio
    tipo: str           # retraso | cancelacion | anden | salida
    valor: str          # lo que se guarda en 'notified' para no repetir
    titulo: str
    cuerpo: str
    train_id: str | None


def _name(t: Train) -> str:
    return f"{t.servicio} {t.numero}".strip()


def _train_alerts(dev: str, ref: str, avisos: dict, t: Train, prev: Snapshot | None, seen) -> list[Alert]:
    out = []
    retraso = t.retraso_min or 0
    if avisos.get("retraso") and retraso >= DELAY_STEP_MIN:
        bucket = retraso // DELAY_STEP_MIN * DELAY_STEP_MIN
        if bucket > int(seen(t.fecha, "retraso") or 0):
            pp = t.proxima_parada
            cuerpo = f"Próxima parada: {pp['nombre']} a las {pp['hora_est']}" if pp else "Retraso en ruta"
            out.append(Alert(dev, ref, t.fecha, "retraso", str(bucket), f"{_name(t)}: +{retraso} min", cuerpo, t.id))
    if avisos.get("cancelacion"):
        suprimidas = [p["nombre"] for p in t.paradas if p["estado"] == "suprimida"]
        valor = "cancelado" if t.cancelado else f"sup:{len(suprimidas)}" if suprimidas else ""
        if valor and valor != seen(t.fecha, "cancelacion"):
            titulo = f"{_name(t)}: cancelado" if t.cancelado else f"{_name(t)}: paradas suprimidas"
            cuerpo = "El tren figura como cancelado" if t.cancelado else "No para en: " + ", ".join(suprimidas)
            out.append(Alert(dev, ref, t.fecha, "cancelacion", valor, titulo, cuerpo, t.id))
    old = prev.trains.get(t.id) if prev else None
    if avisos.get("anden") and t.anden and old and old.anden and old.anden != t.anden \
            and seen(t.fecha, "anden") != t.anden:
        out.append(Alert(dev, ref, t.fecha, "anden", t.anden, f"{_name(t)}: cambio de andén",
                         f"Ahora andén {t.anden} (antes {old.anden})", t.id))
    return out


def diff(prev: Snapshot | None, curr: Snapshot, favs: list[dict],
         notified: dict[tuple[str, str, str, str], str], departures: dict[str, dict], now: float) -> list[Alert]:
    """Avisos que hay que enviar ahora. No hace E/S.

    favs: favoritos {device_id, tipo, ref, avisos}. Solo se usan los de tipo 'tren' (ref = número).
    notified: último valor enviado por (device_id, ref, fecha, tipo).
    departures: por número de tren, {ts, origen, fecha} de su primera salida de hoy.
    """
    by_num: dict[str, Train] = {}
    for t in curr.trains.values():
        by_num.setdefault(t.numero, t)
    out: list[Alert] = []
    for f in favs:
        if f["tipo"] != "tren":
            continue
        dev, ref, avisos = f["device_id"], f["ref"], f["avisos"]

        def seen(fecha: str, tipo: str, dev=dev, ref=ref) -> str | None:
            return notified.get((dev, ref, fecha, tipo))

        t = by_num.get(ref)
        if t:
            out += _train_alerts(dev, ref, avisos, t, prev, seen)
        dep = departures.get(ref)
        if avisos.get("salida") and dep and 0 <= dep["ts"] - now <= DEPARTURE_WINDOW_S \
                and not seen(dep["fecha"], "salida"):
            out.append(Alert(dev, ref, dep["fecha"], "salida", "1", f"Tren {ref}: sale pronto",
                             f"Sale de {dep['origen']} a las {hhmm(dep['ts'])}", t.id if t else None))
    return out
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_alerts_diff.py -v` → 6 passed

- [ ] **Step 5: Commit**

```bash
git add api/app/alerts/diff.py api/tests/test_alerts_diff.py
git commit -m "feat(api): lógica de avisos de retraso, cancelación, andén y salida"
```

---

### Task 13: Envío Web Push y orquestación de avisos

**Files:**
- Create: `api/app/alerts/push.py`, `api/app/alerts/run.py`, `api/scripts/gen_vapid.py`
- Test: `api/tests/test_alerts_run.py`

- [ ] **Step 1: Test que falla** — `tests/test_alerts_run.py`

```python
from app import appdb
from app.alerts.run import process
from app.realtime.snapshot import build_snapshot
from tests.helpers import NOW

SUB = {"endpoint": "https://push.example.test/abc", "keys": {"p256dh": "k", "auth": "a"}}
ALL = {"retraso": True, "cancelacion": True, "anden": True, "salida": True}


def setup(client, salida=False):
    st = client.app.state.st
    appdb.put_favorite(st.app_db, "device-0001", "tren", "03304", {**ALL, "salida": salida})
    appdb.put_subscription(st.app_db, "device-0001", SUB)
    return st


def test_sends_once_and_records(client):
    st = setup(client)
    sent = []

    def send(settings, sub, payload):
        sent.append((sub, payload))
        return "ok"

    alerts = process(st, send=send)
    assert [(a.tipo, a.valor) for a in alerts] == [("retraso", "5")]
    assert sent[0][0] == SUB
    assert sent[0][1] == {"title": "AVE 03304: +5 min",
                          "body": "Próxima parada: Zaragoza Delicias a las 11:25",
                          "url": "/t/LD:03304", "tag": "03304-retraso"}
    assert appdb.notified_map(st.app_db) == {("device-0001", "03304", "2026-11-11", "retraso"): "5"}
    assert process(st, send=send) == [] and len(sent) == 1       # no repite


def test_gone_subscription_is_deleted(client):
    st = setup(client)
    process(st, send=lambda *a: "gone")
    assert appdb.get_subscription(st.app_db, "device-0001") is None


def test_departure_alert_uses_schedule(client):
    st = setup(client, salida=True)
    st.clock = lambda: NOW - 3600 - 300          # 09:55: el AVE sale de Atocha a las 10:00
    st.snapshot = build_snapshot({}, st.repo, None, st.clock())
    alerts = process(st, send=lambda *a: "ok")
    assert [(a.tipo, a.cuerpo) for a in alerts] == [("salida", "Sale de Madrid-Puerta de Atocha a las 10:00")]


def test_no_favorites_does_nothing(client):
    assert process(client.app.state.st, send=lambda *a: 1 / 0) == []


def test_no_subscription_still_records(client):
    st = client.app.state.st
    appdb.put_favorite(st.app_db, "device-0001", "tren", "03304", ALL)
    assert len(process(st, send=lambda *a: 1 / 0)) == 1          # sin suscripción no se llama a send
    assert len(appdb.notified_map(st.app_db)) == 1
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_alerts_run.py -v` → FAIL (`ModuleNotFoundError: app.alerts.run`)

- [ ] **Step 3: Implementación**

`app/alerts/push.py`:
```python
import json
import logging

from pywebpush import WebPushException, webpush

from ..config import Settings

log = logging.getLogger(__name__)


def send_push(settings: Settings, sub: dict, payload: dict) -> str:
    """Devuelve 'ok', 'gone' (la suscripción ya no existe: borrarla) o 'error'."""
    if not settings.vapid_private_key or not settings.vapid_subject:
        log.warning("Push sin configurar (faltan VAPID_PRIVATE_KEY o VAPID_SUBJECT)")
        return "error"
    try:
        webpush(subscription_info=sub, data=json.dumps(payload),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject})
        return "ok"
    except WebPushException as exc:
        code = getattr(exc.response, "status_code", None)
        log.warning("Push falló (%s)", code)
        return "gone" if code in (404, 410) else "error"
```

`app/alerts/run.py`:
```python
from collections.abc import Callable

from .. import appdb
from ..state import State
from ..timeutil import madrid_date, service_midnight
from .diff import Alert, diff
from .push import send_push


def _departures(st: State, favs: list[dict], now: float) -> dict[str, dict]:
    today = madrid_date(now)
    out: dict[str, dict] = {}
    for f in favs:
        ref = f["ref"]
        if f["tipo"] == "tren" and f["avisos"].get("salida") and ref not in out:
            row = st.repo.first_departure(ref, today)
            if row:
                out[ref] = {"ts": service_midnight(today) + row["dep"], "origen": row["origen"],
                            "fecha": today.isoformat()}
    return out


def process(st: State, send: Callable = send_push) -> list[Alert]:
    """Calcula los avisos del snapshot actual, los envía y los registra para no repetirlos."""
    favs = [f for f in appdb.list_favorites(st.app_db) if f["tipo"] == "tren"]
    if not favs:
        return []
    now = st.clock()
    alerts = diff(st.prev, st.snapshot, favs, appdb.notified_map(st.app_db), _departures(st, favs, now), now)
    for a in alerts:
        sub = appdb.get_subscription(st.app_db, a.device_id)
        if sub:
            payload = {"title": a.titulo, "body": a.cuerpo,
                       "url": f"/t/{a.train_id}" if a.train_id else "/", "tag": f"{a.ref}-{a.tipo}"}
            if send(st.settings, sub, payload) == "gone":
                appdb.delete_subscription(st.app_db, a.device_id)
        appdb.set_notified(st.app_db, a.device_id, a.ref, a.fecha, a.tipo, a.valor)
    return alerts
```

`scripts/gen_vapid.py`:
```python
"""Genera las claves VAPID para Web Push. Uso: python scripts/gen_vapid.py <carpeta_de_datos>"""
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from py_vapid.utils import b64urlencode

out = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
out.mkdir(parents=True, exist_ok=True)
pem = out / "vapid_private.pem"
if pem.exists():
    sys.exit(f"Ya existe {pem}; bórralo si quieres generar otra clave.")
vapid = Vapid01()
vapid.generate_keys()
vapid.save_key(str(pem))
raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print(f"Clave privada guardada en {pem}")
print(f"VAPID_PUBLIC_KEY={b64urlencode(raw)}")
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_alerts_run.py -v` → 5 passed

- [ ] **Step 5: Probar el generador de claves**

Run: `.venv/Scripts/python scripts/gen_vapid.py ../data`
Expected: imprime `Clave privada guardada en ..\data\vapid_private.pem` y una línea `VAPID_PUBLIC_KEY=B…` de 87 caracteres tras el `=`. Guardar esa línea para el Task 15.

- [ ] **Step 6: Commit**

```bash
git add api/app/alerts/push.py api/app/alerts/run.py api/scripts/gen_vapid.py api/tests/test_alerts_run.py
git commit -m "feat(api): envío Web Push y orquestación de avisos"
```

---

### Task 14: Descarga de horarios y bucles de fondo

**Files:**
- Create: `api/app/gtfs_static/loader.py`
- Modify: `api/app/main.py` (lifespan con los dos bucles)
- Test: `api/tests/test_loader.py`, `api/tests/test_background.py`

- [ ] **Step 1: Test que falla** — `tests/test_loader.py`

```python
import os

import pytest

from app.config import Settings
from app.gtfs_static.loader import needs_refresh, refresh_gtfs, validate
from app.gtfs_static.repo import GtfsRepo
from tests.helpers import NOW, gtfs_sources, make_zip


def test_validate():
    validate(gtfs_sources()["LD"], min_bytes=0)
    with pytest.raises(ValueError, match="pequeño"):
        validate(gtfs_sources()["LD"], min_bytes=10_000_000)
    with pytest.raises(ValueError, match="trips.txt"):
        validate(make_zip({"stops.txt": "stop_id\n"}), min_bytes=0)
    with pytest.raises(ValueError, match="zip"):
        validate(b"esto no es un zip", min_bytes=0)


def test_refresh_builds_db(tmp_path):
    settings = Settings(data_dir=tmp_path, gtfs_min_bytes=0)
    by_url = dict(zip(settings.gtfs_urls.values(), gtfs_sources().values()))
    refresh_gtfs(settings, download=by_url.__getitem__)
    assert GtfsRepo(settings.gtfs_db).trip("LD", "0330412026-11-11") is not None


def test_failed_refresh_keeps_previous_db(tmp_path):
    settings = Settings(data_dir=tmp_path, gtfs_min_bytes=0)
    by_url = dict(zip(settings.gtfs_urls.values(), gtfs_sources().values()))
    refresh_gtfs(settings, download=by_url.__getitem__)
    with pytest.raises(ValueError):
        refresh_gtfs(settings, download=lambda url: b"corrupto")
    assert GtfsRepo(settings.gtfs_db).trip("LD", "0330412026-11-11") is not None


def test_needs_refresh(tmp_path):
    path = tmp_path / "gtfs.db"
    assert needs_refresh(path, NOW) is True                       # no existe
    path.write_bytes(b"x")
    os.utime(path, (NOW - 3600, NOW - 3600))
    assert needs_refresh(path, NOW) is False                      # es de hoy
    os.utime(path, (NOW - 86400, NOW - 86400))
    assert needs_refresh(path, NOW) is True                       # es de ayer y son las 11:00
    assert needs_refresh(path, NOW - 9 * 3600) is False           # 02:00: aún no toca
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `pytest tests/test_loader.py -v` → FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implementación** — `app/gtfs_static/loader.py`

```python
import io
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx

from ..config import Settings
from ..timeutil import MADRID, madrid_date
from .store import build_gtfs_db

REQUIRED = ("trips.txt", "stops.txt", "stop_times.txt", "routes.txt")
REFRESH_FROM_HOUR = 3


def download(url: str) -> bytes:
    resp = httpx.get(url, timeout=180, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def validate(raw: bytes, min_bytes: int) -> None:
    if len(raw) < min_bytes:
        raise ValueError(f"GTFS demasiado pequeño ({len(raw)} bytes)")
    try:
        names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
    except zipfile.BadZipFile as exc:
        raise ValueError("El GTFS descargado no es un zip válido") from exc
    for name in REQUIRED:
        if name not in names:
            raise ValueError(f"Al GTFS le falta {name}")


def refresh_gtfs(settings: Settings, download: Callable[[str], bytes] = download) -> None:
    """Descarga y valida los dos zips y reconstruye gtfs.db. Si algo falla, la base anterior queda intacta."""
    sources = {}
    for source, url in settings.gtfs_urls.items():
        raw = download(url)
        validate(raw, settings.gtfs_min_bytes)
        sources[source] = raw
    build_gtfs_db(settings.gtfs_db, sources)


def needs_refresh(path: Path, now: float) -> bool:
    """True si no hay base, o si es de un día anterior y ya son las 03:00 (hora de Madrid)."""
    if not path.exists():
        return True
    is_old = madrid_date(path.stat().st_mtime) < madrid_date(now)
    return is_old and datetime.fromtimestamp(now, MADRID).hour >= REFRESH_FROM_HOUR
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `pytest tests/test_loader.py -v` → 4 passed

- [ ] **Step 5: Test que falla para los bucles** — `tests/test_background.py`

```python
import asyncio

from app import appdb
from app.main import tick
from tests.conftest import sample_feeds
from tests.helpers import NOW


class FakeFetcher:
    async def fetch_all(self, now):
        return sample_feeds()


def test_tick_builds_snapshot_and_runs_alerts(client):
    st = client.app.state.st
    first = st.snapshot
    appdb.put_favorite(st.app_db, "device-0001", "tren", "03304", {"retraso": True})
    asyncio.run(tick(st, FakeFetcher()))
    assert st.prev is first and st.snapshot is not first
    assert set(st.snapshot.trains) == {"LD:03304", "CER:35903"}
    assert ("device-0001", "03304", "2026-11-11", "retraso") in appdb.notified_map(st.app_db)


def test_tick_waits_for_gtfs(client):
    st = client.app.state.st
    st.settings.gtfs_db.unlink()
    before = st.snapshot
    asyncio.run(tick(st, FakeFetcher()))
    assert st.snapshot is before
```

- [ ] **Step 6: Ejecutar y ver que falla**

Run: `pytest tests/test_background.py -v` → FAIL (`ImportError: cannot import name 'tick'`)

- [ ] **Step 7: Implementación** — sustituir `app/main.py` completo por:

```python
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI

from . import appdb
from .alerts.run import process
from .api import stations, trains, user
from .config import Settings
from .gtfs_static.loader import needs_refresh, refresh_gtfs
from .realtime.fetch import FeedFetcher
from .realtime.snapshot import build_snapshot
from .state import State

log = logging.getLogger(__name__)
GTFS_CHECK_SECONDS = 1800


async def tick(st: State, fetcher) -> None:
    """Un ciclo: descargar feeds, construir el snapshot y procesar avisos."""
    if not st.settings.gtfs_db.exists():
        return    # todavía se están descargando los horarios
    now = st.clock()
    feeds = await fetcher.fetch_all(now)
    snap = await asyncio.to_thread(build_snapshot, feeds, st.repo, st.snapshot, now)
    st.prev, st.snapshot = st.snapshot, snap
    await asyncio.to_thread(process, st)


async def poll_loop(st: State) -> None:
    async with httpx.AsyncClient(headers={"User-Agent": "TrainRadar24h"}) as client:
        fetcher = FeedFetcher(st.settings.feed_urls, client)
        while True:
            try:
                await tick(st, fetcher)
            except Exception:
                log.exception("Fallo en el ciclo de tiempo real")
            await asyncio.sleep(st.settings.poll_seconds)


async def gtfs_loop(st: State) -> None:
    while True:
        try:
            if needs_refresh(st.settings.gtfs_db, st.clock()):
                log.info("Actualizando horarios GTFS…")
                await asyncio.to_thread(refresh_gtfs, st.settings)
                st.repo.reload()
                log.info("Horarios GTFS actualizados")
        except Exception:
            log.exception("No se pudieron actualizar los horarios; se mantiene la versión anterior")
        await asyncio.sleep(GTFS_CHECK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = []
    if app.state.background:
        tasks = [asyncio.create_task(gtfs_loop(app.state.st)), asyncio.create_task(poll_loop(app.state.st))]
    yield
    for task in tasks:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app(settings: Settings | None = None, background: bool = True) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or Settings()
    appdb.init(settings.app_db)
    app = FastAPI(title="TrainRadar24h API", lifespan=lifespan)
    app.state.st = State(settings)
    app.state.background = background
    app.include_router(trains.router)
    app.include_router(stations.router)
    app.include_router(user.router)
    return app
```

- [ ] **Step 8: Ejecutar toda la batería**

Run: `pytest -v` → todo en verde (68 tests, ningún fallo)

- [ ] **Step 9: Commit**

```bash
git add api/app/gtfs_static/loader.py api/app/main.py api/tests/test_loader.py api/tests/test_background.py
git commit -m "feat(api): refresco diario de horarios y bucle de tiempo real"
```

---

### Task 15: Docker y prueba real de extremo a extremo

**Files:**
- Create: `api/Dockerfile`, `api/.dockerignore`, `docker-compose.yml`, `.env.example`

- [ ] **Step 1: Ficheros de Docker**

`api/Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
ENV DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

`api/.dockerignore`:
```
.venv
tests
__pycache__
*.egg-info
.pytest_cache
```

`docker-compose.yml` (raíz):
```yaml
services:
  api:
    build: ./api
    restart: unless-stopped
    env_file: .env
    environment:
      VAPID_PRIVATE_KEY: /data/vapid_private.pem
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status == 200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 120s
```

`.env.example` (raíz):
```
# Copiar a .env. La clave pública la imprime: python api/scripts/gen_vapid.py data
VAPID_PUBLIC_KEY=
# Contacto que exige Web Push, con formato mailto:direccion
VAPID_SUBJECT=
```

- [ ] **Step 2: Crear `.env`** (raíz; no se sube a git)

Copiar `.env.example` a `.env`, pegar la `VAPID_PUBLIC_KEY` del Task 13 y pedir al usuario la dirección de contacto para `VAPID_SUBJECT` (formato `mailto:…`). No inventarla.

- [ ] **Step 3: Arrancar**

```bash
docker compose up -d --build
```
```bash
docker compose logs -f api
```
Expected: en 1–2 minutos aparece `Actualizando horarios GTFS…` y después `Horarios GTFS actualizados`. No debe haber trazas de error.

- [ ] **Step 4: Verificar contra los datos reales**

```bash
curl -s http://localhost:8000/api/health
```
Expected: `trenes` > 50 (de día), `feeds.LD` y `feeds.CER` presentes y `gtfs_cargado` con fecha de hoy. Anotar `feeds.LD.edad_s`: el 2026-11-11 iba unos 3600 s por detrás; si sigue así, es un dato a mostrar en la PWA, no un fallo del servidor.

```bash
curl -s http://localhost:8000/api/trains | python -c "import json,sys; d=json.load(sys.stdin)['trenes']; print(len(d)); print(d[0])"
```
Expected: lista con `id`, `lat`, `lon`, `servicio`, `retraso_min`.

```bash
curl -s "http://localhost:8000/api/search?q=atocha"
```
Expected: estaciones de Atocha. Con un `id` de la respuesta:

```bash
curl -s "http://localhost:8000/api/stations/60000/board?tipo=salidas"
```
Expected: filas con `hora_prog`, `destino`, `servicio`; algunas con `train_id` y `retraso_min`. (Si `60000` no existe en los datos reales, usar un `id` devuelto por la búsqueda.)

Comprobar además con un `id` de `/api/trains`: `curl -s http://localhost:8000/api/trains/<id>` devuelve `paradas` y `shape`.

- [ ] **Step 5: Comprobar el porcentaje de trenes casados**

```bash
curl -s http://localhost:8000/api/trains | python -c "import json,sys,urllib.request as u; ts=json.load(sys.stdin)['trenes']; ok=sum(json.load(u.urlopen('http://localhost:8000/api/trains/'+t['id']))['casado_con_horario'] for t in ts); print(ok, '/', len(ts))"
```
Expected: en torno al 100 % en LD y al 80 % en Cercanías (en la investigación: 104/104 y 114/137). Si sale muy por debajo, revisar `service_date` y la normalización antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add api/Dockerfile api/.dockerignore docker-compose.yml .env.example
git commit -m "feat: contenedor Docker de la API y docker-compose"
```

---

## Cobertura del spec

| Sección del spec | Tarea |
|---|---|
| §2 Fuentes de datos, rarezas de los CSV | 2, 3, 14 |
| §3 Unidades `gtfs_static`, `realtime`, `alerts`, `api` | 2–14 |
| §4 Flujo en tiempo real (cruce, retrasos, próxima parada, rumbo, andén, ETag) | 6, 7, 14 |
| §5 API REST | 9, 10, 11 |
| §7 Avisos push | 12, 13 |
| §8 Errores y resiliencia | 7 (feeds), 14 (horarios), 15 (health check) |
| §9 Pruebas de backend | todas |
| §6 Pantallas de la PWA, service worker, HTTPS para el móvil | **segundo plan (web)** |
