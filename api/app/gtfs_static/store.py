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
