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
