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
