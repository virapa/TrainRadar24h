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
