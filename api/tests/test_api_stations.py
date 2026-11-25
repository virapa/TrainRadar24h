def test_near(client):
    body = client.get("/api/stations/near", params={"lat": 41.6587, "lon": -0.9113}).json()
    assert body[0]["id"] == "04040" and body[0]["dist_m"] == 0


def test_departures_board_applies_live_delay(client):
    body = client.get("/api/stations/04040/board", params={"tipo": "salidas"}).json()
    assert body["estacion"]["nombre"] == "Zaragoza Delicias"
    row = body["filas"][0]
    assert (row["hora_prog"], row["hora_est"], row["retraso_min"]) == ("11:22", "11:27", 5)
    assert (row["destino"], row["servicio"], row["numero"]) == ("Barcelona-Sants", "AVE", "03304")
    assert (row["train_id"], row["estado"], row["anden"]) == ("LD:03304", "en_circulacion", None)


def test_arrivals_board(client):
    body = client.get("/api/stations/71801/board", params={"tipo": "llegadas"}).json()
    row = body["filas"][0]
    assert (row["hora_prog"], row["hora_est"], row["origen"]) == ("12:45", "12:50", "Madrid-Puerta de Atocha")


def test_board_outside_window_is_empty(client):
    # El Cercanías salió de Príncipe Pío a las 10:00; son las 11:00 y la ventana empieza a las 10:30.
    assert client.get("/api/stations/18002/board", params={"tipo": "salidas"}).json()["filas"] == []


def test_board_without_live_train_is_scheduled(client):
    client.app.state.st.snapshot.trains.clear()
    client.app.state.st.snapshot.__dict__.pop("by_trip", None)
    row = client.get("/api/stations/04040/board", params={"tipo": "salidas"}).json()["filas"][0]
    assert (row["hora_est"], row["retraso_min"], row["train_id"], row["estado"]) == (
        "11:22", None, None, "programado")


def test_board_errors(client):
    assert client.get("/api/stations/00000/board", params={"tipo": "salidas"}).status_code == 404
    assert client.get("/api/stations/04040/board", params={"tipo": "otra"}).status_code == 422


def test_dedupe_keeps_one_row_per_train_and_time():
    # Renfe publica un viaje por cada variante de recorrido del mismo tren: mismo número y misma hora.
    from app.api.stations import dedupe

    rows = [
        {"numero": "00192", "ts_prog": 100, "train_id": None, "destino": "A"},
        {"numero": "00192", "ts_prog": 100, "train_id": "LD:00192", "destino": "B"},
        {"numero": "00192", "ts_prog": 900, "train_id": None, "destino": "A"},
        {"numero": "03304", "ts_prog": 100, "train_id": None, "destino": "C"},
        {"numero": "03304", "ts_prog": 100, "train_id": None, "destino": "D"},
    ]
    out = dedupe(rows)
    assert [(r["numero"], r["ts_prog"], r["destino"]) for r in out] == [
        ("00192", 100, "B"),    # gana la variante que está circulando
        ("03304", 100, "C"),    # sin tren en circulación, gana la primera
        ("00192", 900, "A"),
    ]
