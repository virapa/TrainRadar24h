import hashlib
import json
import re
from datetime import date, timedelta

from ..geo import bearing, haversine_m
from ..gtfs_static.repo import GtfsRepo, TripInfo
from ..timeutil import hhmm, madrid_date, service_midnight
from .models import Feed, Snapshot, Train

LABEL_RE = re.compile(r"^(?P<linea>[^-]+)-(?P<num>\d+)(?:-PLATF\.\((?P<anden>[^)]+)\))?")
DEFAULT_COLOR = "#9AA0A6"
MIN_MOVE_M = 30


def parse_label(label: str) -> tuple[str | None, str | None, str | None]:
    """'C5-35903-PLATF.(3)' → ('C5', '35903', '3'). Si no tiene ese formato, todo None."""
    m = LABEL_RE.match(label or "")
    return (m["linea"], m["num"], m["anden"]) if m else (None, None, None)


def service_date(trip: TripInfo, trip_id: str, now: float) -> date:
    """Día en que circula el viaje: hoy o ayer, según en cuál encaja el horario con la hora actual.

    El sufijo de fecha del trip_id de LD NO sirve: es el inicio de validez del horario, y el mismo
    trip_id se reutiliza todos los días del periodo.
    """
    today = madrid_date(now)
    for d in (today, today - timedelta(days=1)):
        base = service_midnight(d)
        if base + trip.stops[0].dep - 3600 <= now <= base + trip.stops[-1].arr + 3 * 3600:
            return d
    return today


def _is_canceled(tu: dict) -> bool:
    return tu.get("trip", {}).get("scheduleRelationship") == "CANCELED"


def _delays(tus: list[dict]) -> tuple[dict[str, int], set[str], int | None, bool]:
    """Fusiona los tripUpdate no cancelados de un viaje: retraso por parada (s), paradas suprimidas,
    retraso global y si alguno trae detalle por parada. El posterior sobrescribe al anterior."""
    delays: dict[str, int] = {}
    skipped: set[str] = set()
    base_delay = None
    detailed = False
    for tu in tus:
        if _is_canceled(tu):
            continue
        if tu.get("delay") is not None:
            base_delay = tu["delay"]
        for stu in tu.get("stopTimeUpdate", []):
            detailed = True
            event = stu.get("arrival") or stu.get("departure") or {}
            if "delay" in event:
                delays[stu.get("stopId")] = int(event["delay"])
            if stu.get("scheduleRelationship") == "SKIPPED":
                skipped.add(stu.get("stopId"))
    return delays, skipped, base_delay, detailed


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
    # Sin posición anterior no hay rumbo medido: se orienta hacia la próxima parada.
    if train.rumbo is None and nxt["lat"] is not None \
            and haversine_m(train.lat, train.lon, nxt["lat"], nxt["lon"]) > MIN_MOVE_M:
        train.rumbo = round(bearing(train.lat, train.lon, nxt["lat"], nxt["lon"]))
    if trip.numero:
        train.numero = trip.numero
    if trip.color:
        train.color = f"#{trip.color}"
    if train.source == "CER":
        train.linea = trip.route_short or train.linea
    else:
        train.servicio = trip.route_short


def _train_id(src: str, v: dict) -> str:
    return f"{src}:{v.get('vehicle', {}).get('id') or v.get('trip', {}).get('tripId', '')}"


def _rank(src: str, v: dict, repo: GtfsRepo) -> tuple[bool, bool, int, int]:
    """Preferencia entre entidades del mismo tren (variantes de recorrido): mayor es mejor."""
    trip_id = v.get("trip", {}).get("tripId", "")
    trip = repo.trip(src, trip_id) if trip_id else None
    stop_ids = [st.stop_id for st in trip.stops] if trip else []
    idx = stop_ids.index(v["stopId"]) if v.get("stopId") in stop_ids else -1
    return idx >= 0, trip is not None, len(stop_ids), idx


def _build_train(src: str, v: dict, tus: dict[str, list[dict]], repo: GtfsRepo,
                 prev: Snapshot | None, now: float, feed_ts: int) -> Train:
    trip_id = v.get("trip", {}).get("tripId", "")
    veh = v.get("vehicle", {})
    vid = veh.get("id") or trip_id
    linea, num, anden = parse_label(veh.get("label", ""))
    tid = _train_id(src, v)
    lat, lon = v["position"]["latitude"], v["position"]["longitude"]
    old = prev.trains.get(tid) if prev else None
    rumbo = old.rumbo if old else None
    if old and haversine_m(old.lat, old.lon, lat, lon) > MIN_MOVE_M:
        rumbo = round(bearing(old.lat, old.lon, lat, lon))
    trip_tus = tus.get(trip_id, [])
    delays, skipped, base_delay, detailed = _delays(trip_tus)
    train = Train(
        id=tid, source=src, trip_id=trip_id, fecha=madrid_date(now).isoformat(), numero=num or vid,
        servicio="CERCANIAS" if src == "CER" else "LD", linea=linea if src == "CER" else None,
        color=DEFAULT_COLOR, lat=lat, lon=lon, rumbo=rumbo,
        estado=v.get("currentStatus", "IN_TRANSIT_TO"), origen=None, destino=None, proxima_parada=None,
        retraso_min=round(base_delay / 60) if base_delay is not None else None, anden=anden,
        progreso=None, casado_con_horario=False, cancelado=False,
        ts=int(v.get("timestamp", feed_ts)))
    trip = repo.trip(src, trip_id) if trip_id else None
    matched = bool(trip and trip.stops)
    if matched:
        # Renfe marca TODAS las paradas como SKIPPED (más una entidad CANCELED) en muchos trenes que
        # siguen circulando con posición y retraso: es contradictorio, y el trip_id no lleva el día,
        # así que esas marcas pueden ser de otra fecha. Si están todas suprimidas, no se usan.
        if all(st.stop_id in skipped for st in trip.stops):
            skipped = set()
        _apply_schedule(train, trip, v, delays, skipped, base_delay, now)
    # Una entidad CANCELED acompaña a cualquier supresión parcial; solo cuenta como cancelación
    # si no hay ningún detalle por parada.
    train.cancelado = any(map(_is_canceled, trip_tus)) and not detailed
    return train


def build_snapshot(feeds: dict[str, Feed], repo: GtfsRepo, prev: Snapshot | None, now: float) -> Snapshot:
    """Cruza los feeds en vivo con los horarios. No hace E/S de red; solo lee del repo."""
    trains: dict[str, Train] = {}
    info: dict[str, dict] = {}
    for src in ("LD", "CER"):
        vp = feeds.get(f"{src}_vp")
        if not vp:
            continue
        tu_feed = feeds.get(f"{src}_tu")
        # La cabecera de vehicle_positions_LD llega con una hora de desfase fijo (la de
        # trip_updates_LD es correcta), así que se toma la más reciente de las dos.
        feed_ts = max(vp.timestamp, tu_feed.timestamp if tu_feed else 0)
        info[src] = {"edad_s": max(0, int(now - feed_ts)), "stale": vp.stale}
        tus: dict[str, list[dict]] = {}
        for e in (tu_feed.entities if tu_feed else []):
            if "tripUpdate" in e:
                tus.setdefault(e["tripUpdate"].get("trip", {}).get("tripId"), []).append(e["tripUpdate"])
        # El mismo vehículo puede venir una vez por variante de recorrido: se elige una sola entidad.
        groups: dict[str, list[dict]] = {}
        for e in vp.entities:
            v = e.get("vehicle")
            if v and "position" in v:
                groups.setdefault(_train_id(src, v), []).append(v)
        for tid, vs in groups.items():
            best = max(vs, key=lambda v: _rank(src, v, repo))   # a igualdad, la primera del feed
            trains[tid] = _build_train(src, best, tus, repo, prev, now, feed_ts)
    payload = json.dumps([trains[k].light() for k in sorted(trains)], sort_keys=True)
    return Snapshot(trains, now, info, hashlib.sha1(payload.encode()).hexdigest())
