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
