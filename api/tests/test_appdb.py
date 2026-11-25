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
