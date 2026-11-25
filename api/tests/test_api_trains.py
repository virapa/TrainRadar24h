def test_health(client):
    body = client.get("/api/health").json()
    assert body["trenes"] == 2
    assert body["feeds"]["LD"] == {"edad_s": 0, "stale": False}
    assert body["gtfs_cargado"] is not None
    assert body["version"] == "dev"


def test_trains_list_is_light_and_has_etag(client):
    r = client.get("/api/trains")
    assert r.status_code == 200
    body = r.json()
    assert {t["id"] for t in body["trenes"]} == {"LD:03304", "CER:35903"}
    assert "paradas" not in body["trenes"][0]
    assert set(body["feeds"]) == {"LD", "CER"}
    etag = r.headers["etag"]
    again = client.get("/api/trains", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""


def test_train_detail(client):
    t = client.get("/api/trains/LD:03304").json()
    assert (t["servicio"], t["destino"], t["retraso_min"]) == ("AVE", "Barcelona-Sants", 5)
    assert [p["estado"] for p in t["paradas"]] == ["pasada", "proxima", "pendiente"]
    assert t["shape"] == [[-3.6902, 40.4066], [-0.9113, 41.6587], [2.14, 41.379]]   # sin shape: paradas
    assert client.get("/api/trains/LD:99999").status_code == 404


def test_unmatched_train_detail_has_empty_shape(client):
    t = client.get("/api/trains/CER:35903").json()
    assert (t["linea"], t["anden"], t["paradas"], t["shape"]) == ("C5", "3", [], [])


def test_search(client):
    by_number = client.get("/api/search", params={"q": "033"}).json()
    assert [t["id"] for t in by_number["trenes"]] == ["LD:03304"]
    assert by_number["estaciones"] == []
    by_name = client.get("/api/search", params={"q": "zarag"}).json()
    assert [s["id"] for s in by_name["estaciones"]] == ["04040"]
    assert by_name["trenes"] == []
    assert client.get("/api/search", params={"q": "z"}).json() == {"trenes": [], "estaciones": []}
