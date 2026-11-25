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
    return {"estacion": stop, "tipo": tipo, "filas": dedupe(filas)}


def dedupe(filas: list[dict]) -> list[dict]:
    """Una fila por tren y hora, ordenadas por hora.

    Renfe publica un viaje por cada variante de recorrido del mismo tren, así que el mismo número
    aparece varias veces a la misma hora. Se conserva la variante que está circulando o, si no hay,
    la primera.
    """
    best: dict[tuple[str, int], dict] = {}
    for fila in filas:
        key = (fila["numero"], fila["ts_prog"])
        if key not in best or (fila["train_id"] and not best[key]["train_id"]):
            best[key] = fila
    return sorted(best.values(), key=lambda f: f["ts_prog"])
