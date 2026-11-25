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
