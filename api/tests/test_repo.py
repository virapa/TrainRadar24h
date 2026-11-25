from datetime import date

D = date(2026, 11, 11)


def test_trip_with_stops(repo):
    t = repo.trip("LD", "0330412026-11-11")
    assert (t.numero, t.route_short, t.color) == ("03304", "AVE", "FF0000")
    assert [s.stop_id for s in t.stops] == ["60000", "04040", "71801"]
    assert (t.stops[1].name, t.stops[1].arr, t.stops[1].dep) == ("Zaragoza Delicias", 40800, 40920)
    assert repo.trip("LD", "no-existe") is None


def test_shape(repo):
    assert repo.shape("10_C1") == [[-3.72, 40.421], [-3.6895, 40.4065]]
    assert repo.shape("nada") == []


def test_search_stops_ignores_accents_and_case(repo):
    assert [s["id"] for s in repo.search_stops("CHAMARTIN")] == ["17000"]
    assert [s["id"] for s in repo.search_stops("príncipe")] == ["18002"]
    assert {s["id"] for s in repo.search_stops("madrid")} == {"60000", "17000", "18000"}


def test_near(repo):
    near = repo.near(40.4066, -3.6902, limit=2)
    assert {s["id"] for s in near} == {"60000", "18000"}
    assert near[0]["dist_m"] <= near[1]["dist_m"]


def test_board_departures_and_arrivals(repo):
    sal = repo.board("04040", D, 0, 86400, "salidas")
    assert len(sal) == 1
    assert (sal[0]["numero"], sal[0]["destino"], sal[0]["origen"], sal[0]["dep"]) == (
        "03304", "Barcelona-Sants", "Madrid-Puerta de Atocha", 40920)
    assert repo.board("71801", D, 0, 86400, "salidas") == []      # última parada: no sale
    assert len(repo.board("71801", D, 0, 86400, "llegadas")) == 1
    assert repo.board("60000", D, 0, 86400, "llegadas") == []     # primera parada: no llega


def test_board_respects_calendar(repo):
    assert repo.board("04040", date(2026, 12, 25), 0, 86400, "salidas") == []   # excepción tipo 2
    assert repo.board("18002", date(2026, 11, 12), 0, 86400, "salidas") == []   # 1014X solo el día 11
    assert len(repo.board("18002", D, 0, 86400, "salidas")) == 1


def test_first_departure(repo):
    r = repo.first_departure("03304", D)
    assert (r["source"], r["dep"], r["origen"]) == ("LD", 36000, "Madrid-Puerta de Atocha")
    assert repo.first_departure("19799", D)["source"] == "CER"
    assert repo.first_departure("99999", D) is None


def test_loaded_at(repo, tmp_path):
    from app.gtfs_static.repo import GtfsRepo
    assert repo.loaded_at() is not None
    assert GtfsRepo(tmp_path / "no.db").loaded_at() is None
