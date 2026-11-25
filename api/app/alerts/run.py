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
