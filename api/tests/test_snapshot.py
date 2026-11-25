import json
from pathlib import Path

import pytest

from app.gtfs_static.repo import GtfsRepo
from app.gtfs_static.store import build_gtfs_db
from app.realtime.models import Feed
from app.realtime.snapshot import build_snapshot, parse_label
from tests.helpers import CER_FILES, LD_FILES, NOW, PAD, make_zip

LD_TRIP = "0330412026-11-11"
LD_SHORT = "0330422026-11-11"   # variante corta del mismo tren: solo Zaragoza y Barcelona
FIX = Path(__file__).parent / "fixtures"


def vp(trip_id, lat, lon, stop_id=None, vid="03304", label="03304"):
    v = {"trip": {"tripId": trip_id}, "position": {"latitude": lat, "longitude": lon},
         "currentStatus": "IN_TRANSIT_TO", "vehicle": {"id": vid, "label": label}}
    if stop_id:
        v["stopId"] = stop_id
    return {"id": f"VP_{vid}", "vehicle": v}


def tu(trip_id, updates, rel="SCHEDULED"):
    return {"id": f"TU_{trip_id}", "tripUpdate": {
        "trip": {"tripId": trip_id, "scheduleRelationship": rel}, "stopTimeUpdate": updates}}


def cancel(trip_id):
    """Como en el feed real de LD: entidad CANCELED sin stopTimeUpdate."""
    return {"id": f"TUC_{trip_id}", "tripUpdate": {
        "trip": {"tripId": trip_id, "scheduleRelationship": "CANCELED"}}}


def feed(entities):
    return Feed(entities=entities, timestamp=int(NOW), fetched_at=NOW)


def ld_train(repo, vps, tus=()):
    feeds = {"LD_vp": feed(list(vps)), "LD_tu": feed(list(tus))}
    snap = build_snapshot(feeds, repo, None, NOW)
    assert list(snap.trains) == ["LD:03304"]
    return snap.trains["LD:03304"]


def both_orders(a, b):
    return ([a, b], [b, a])


@pytest.fixture
def repo_variants(tmp_path):
    """Como `repo`, pero el tren 03304 tiene además una variante de solo dos paradas."""
    files = dict(LD_FILES)
    files["trips.txt"] += f"R1,S1,{LD_SHORT},,03304,{PAD}\n"
    files["stop_times.txt"] += (
        f"{LD_SHORT},11:20:00,11:22:00,04040,1\n"
        f"{LD_SHORT},12:45:00,12:45:00,71801,2\n"
    )
    path = tmp_path / "gtfs_variants.db"
    build_gtfs_db(path, {"LD": make_zip(files, "cp1252"), "CER": make_zip(CER_FILES)})
    return GtfsRepo(path)


def test_parse_label():
    assert parse_label("C5-35903-PLATF.(3)") == ("C5", "35903", "3")
    assert parse_label("C1-23537") == ("C1", "23537", None)
    assert parse_label("03304") == (None, None, None)
    assert parse_label("") == (None, None, None)


def test_matched_ld_train_with_delay(repo):
    feeds = {
        "LD_vp": feed([vp(LD_TRIP, 41.0, -2.0, "04040")]),
        "LD_tu": feed([tu(LD_TRIP, [{"stopId": "04040", "arrival": {"delay": 300}}])]),
    }
    t = build_snapshot(feeds, repo, None, NOW).trains["LD:03304"]
    assert (t.servicio, t.numero, t.linea, t.color) == ("AVE", "03304", None, "#FF0000")
    assert (t.origen, t.destino) == ("Madrid-Puerta de Atocha", "Barcelona-Sants")
    assert t.proxima_parada == {"id": "04040", "nombre": "Zaragoza Delicias",
                                "hora_prog": "11:20", "hora_est": "11:25"}
    assert (t.retraso_min, t.progreso, t.casado_con_horario, t.fecha) == (5, 0.5, True, "2026-11-11")
    assert [p["estado"] for p in t.paradas] == ["pasada", "proxima", "pendiente"]
    assert t.paradas[0]["hora_est"] == "10:00"      # antes del primer retraso conocido
    assert t.paradas[2]["hora_est"] == "12:50"      # el retraso se propaga hacia delante


def test_unmatched_cercanias_uses_label(repo):
    feeds = {"CER_vp": feed([vp("3014X35903C5", 37.32, -5.96, "51103", vid="35903",
                                label="C5-35903-PLATF.(3)")])}
    t = build_snapshot(feeds, repo, None, NOW).trains["CER:35903"]
    assert (t.servicio, t.linea, t.numero, t.anden) == ("CERCANIAS", "C5", "35903", "3")
    assert (t.casado_con_horario, t.paradas, t.retraso_min, t.fecha) == (False, [], None, "2026-11-11")


def test_matched_cercanias(repo):
    feeds = {"CER_vp": feed([vp("1014X19799C1", 40.41, -3.70, vid="19799", label="C1-19799-PLATF.(2)")])}
    t = build_snapshot(feeds, repo, None, NOW).trains["CER:19799"]
    assert (t.linea, t.destino, t.anden, t.fecha, t.color) == (
        "C1", "Madrid-Atocha Cercanías", "2", "2026-11-11", "#75B6E0")
    assert t.shape_id == "10_C1"


def test_skipped_stop_and_cancelled_trip(repo):
    skip = [{"stopId": "04040", "scheduleRelationship": "SKIPPED"}]
    # Parada suprimida en un tripUpdate normal: el tren no está cancelado.
    t = ld_train(repo, [vp(LD_TRIP, 41.0, -2.0)], [tu(LD_TRIP, skip)])
    assert [p["estado"] for p in t.paradas] == ["pasada", "suprimida", "proxima"]
    assert t.cancelado is False
    assert t.proxima_parada["id"] == "71801"
    # Los datos de parada de una entidad CANCELED no se usan: solo marca la cancelación.
    t = ld_train(repo, [vp(LD_TRIP, 41.0, -2.0)], [tu(LD_TRIP, skip, rel="CANCELED")])
    assert [p["estado"] for p in t.paradas] == ["pasada", "proxima", "pendiente"]
    assert t.cancelado is True


def test_variants_prefer_trip_with_more_stops(repo_variants):
    a, b = vp(LD_TRIP, 41.0, -2.0, "04040"), vp(LD_SHORT, 41.0, -2.0, "04040")
    for vps in both_orders(a, b):
        t = ld_train(repo_variants, vps)
        assert t.trip_id == LD_TRIP
        assert len(t.paradas) == 3


def test_variants_prefer_entity_with_valid_stop_id(repo_variants):
    a, b = vp(LD_TRIP, 41.0, -2.0), vp(LD_SHORT, 41.0, -2.0, "04040")
    for vps in both_orders(a, b):
        assert ld_train(repo_variants, vps).trip_id == LD_SHORT
    # Un stopId que no es parada del viaje no cuenta como válido.
    a = vp(LD_TRIP, 41.0, -2.0, "99999")
    for vps in both_orders(a, b):
        assert ld_train(repo_variants, vps).trip_id == LD_SHORT


def test_same_trip_twice_prefers_most_advanced_stop(repo_variants):
    a, b = vp(LD_TRIP, 41.0, -2.0, "04040"), vp(LD_TRIP, 41.5, 1.0, "71801")
    for vps in both_orders(a, b):
        t = ld_train(repo_variants, vps)
        assert t.proxima_parada["id"] == "71801"
        assert (t.lat, t.lon) == (41.5, 1.0)


def test_identical_rank_keeps_first_entity(repo_variants):
    a, b = vp(LD_TRIP, 41.0, -2.0, "04040"), vp(LD_TRIP, 41.2, -1.5, "04040")
    assert ld_train(repo_variants, [a, b]).lat == 41.0
    assert ld_train(repo_variants, [b, a]).lat == 41.2


def test_partial_suppression_is_not_cancelled(repo):
    sched = tu(LD_TRIP, [{"stopId": "04040", "arrival": {"delay": 300}},
                         {"stopId": "71801", "scheduleRelationship": "SKIPPED"}])
    for tus in both_orders(sched, cancel(LD_TRIP)):
        t = ld_train(repo, [vp(LD_TRIP, 41.0, -2.0, "04040")], tus)
        assert t.cancelado is False
        assert t.retraso_min == 5
        assert [p["estado"] for p in t.paradas] == ["pasada", "proxima", "suprimida"]


def test_service_date_is_the_running_day_not_the_trip_id_suffix(repo):
    # El sufijo de fecha del trip_id de LD es el inicio de validez del horario, no el día de circulación.
    tomorrow = NOW + 86400
    f = Feed(entities=[vp(LD_TRIP, 41.0, -2.0, "04040")], timestamp=int(tomorrow), fetched_at=tomorrow)
    t = build_snapshot({"LD_vp": f}, repo, None, tomorrow).trains["LD:03304"]
    assert t.fecha == "2026-11-12"
    assert t.paradas[1]["ts_prog"] == t.paradas[1]["ts_est"]
    assert abs(t.paradas[1]["ts_prog"] - (tomorrow + 20 * 60)) < 1   # 11:20 del día 12


def test_unmatched_ld_train_has_generic_service(repo):
    feeds = {"LD_vp": feed([vp("99999L_9172520261112", 41.0, -2.0, vid="99999", label="99999")])}
    t = build_snapshot(feeds, repo, None, NOW).trains["LD:99999"]
    assert (t.servicio, t.casado_con_horario) == ("LD", False)


def test_all_stops_skipped_on_a_live_train_is_ignored(repo):
    # Renfe marca todas las paradas como SKIPPED (más una entidad CANCELED) en trenes que siguen
    # circulando con posición y retraso. Es contradictorio, así que esas marcas no se usan.
    sched = tu(LD_TRIP, [{"stopId": "60000", "scheduleRelationship": "SKIPPED"},
                         {"stopId": "04040", "arrival": {"delay": 300}},
                         {"stopId": "04040", "scheduleRelationship": "SKIPPED"},
                         {"stopId": "71801", "scheduleRelationship": "SKIPPED"}])
    for tus in both_orders(sched, cancel(LD_TRIP)):
        t = ld_train(repo, [vp(LD_TRIP, 41.0, -2.0)], tus)
        assert t.cancelado is False
        assert [p["estado"] for p in t.paradas] == ["pasada", "proxima", "pendiente"]
        assert t.proxima_parada["id"] == "04040"
        assert t.proxima_parada["hora_est"] == "11:25"  # el retraso sí se usa
        assert (t.retraso_min, t.progreso) == (5, 0.5)


def test_only_cancel_entity_is_cancelled(repo):
    t = ld_train(repo, [vp(LD_TRIP, 41.0, -2.0)], [cancel(LD_TRIP)])
    assert t.cancelado is True
    assert [p["estado"] for p in t.paradas] == ["pasada", "proxima", "pendiente"]


def test_merges_several_scheduled_trip_updates(repo):
    first = tu(LD_TRIP, [{"stopId": "04040", "arrival": {"delay": 120}},
                         {"stopId": "71801", "scheduleRelationship": "SKIPPED"}])
    second = tu(LD_TRIP, [{"stopId": "04040", "arrival": {"delay": 300}}])
    t = ld_train(repo, [vp(LD_TRIP, 41.0, -2.0, "04040")], [first, second])
    assert t.retraso_min == 5                          # la entidad posterior sobrescribe
    assert t.paradas[2]["estado"] == "suprimida"       # y lo suprimido en la anterior se conserva
    assert t.cancelado is False


def test_bearing_from_previous_snapshot(repo):
    s1 = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -2.0)])}, repo, None, NOW)
    # Sin posición anterior: rumbo hacia la próxima parada (Zaragoza, al nordeste).
    assert 40 < s1.trains["LD:03304"].rumbo < 60
    s2 =build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -1.9)])}, repo, s1, NOW + 15)
    assert abs(s2.trains["LD:03304"].rumbo - 90) <= 1
    s3 = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -1.9)])}, repo, s2, NOW + 30)
    assert s3.trains["LD:03304"].rumbo == s2.trains["LD:03304"].rumbo   # parado: conserva el rumbo


def test_etag_and_feed_age(repo):
    a = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -2.0)])}, repo, None, NOW)
    b = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.0, -2.0)])}, repo, None, NOW)
    c = build_snapshot({"LD_vp": feed([vp(LD_TRIP, 41.5, -2.0)])}, repo, None, NOW)
    assert a.etag == b.etag != c.etag
    stale = Feed(entities=[], timestamp=int(NOW) - 3600, fetched_at=NOW, stale=True)
    s = build_snapshot({"LD_vp": stale}, repo, None, NOW)
    assert s.feeds["LD"] == {"edad_s": 3600, "stale": True}
    assert "CER" not in s.feeds


def test_unmatched_train_without_history_has_no_bearing(repo):
    feeds = {"CER_vp": feed([vp("3014X35903C5", 37.32, -5.96, vid="35903", label="C5-35903")])}
    assert build_snapshot(feeds, repo, None, NOW).trains["CER:35903"].rumbo is None


def test_feed_age_uses_freshest_header_of_the_source(repo):
    # Renfe publica la cabecera de vehicle_positions_LD con una hora de desfase fijo;
    # la de trip_updates_LD es correcta. La edad y el ts del tren usan la más reciente.
    late_vp = Feed(entities=[vp(LD_TRIP, 41.0, -2.0)], timestamp=int(NOW) - 3600, fetched_at=NOW)
    fresh_tu = Feed(entities=[], timestamp=int(NOW) - 12, fetched_at=NOW)
    s = build_snapshot({"LD_vp": late_vp, "LD_tu": fresh_tu}, repo, None, NOW)
    assert s.feeds["LD"] == {"edad_s": 12, "stale": False}
    assert s.trains["LD:03304"].ts == int(NOW) - 12


def test_real_fixtures_do_not_crash(repo):
    def load(name):
        d = json.loads((FIX / name).read_text(encoding="utf-8"))
        return Feed(entities=d["entity"], timestamp=int(d["header"]["timestamp"]), fetched_at=NOW)

    feeds = {"LD_vp": load("vehicle_positions_LD.json"), "LD_tu": load("trip_updates_LD.json"),
             "CER_vp": load("vehicle_positions.json"), "CER_tu": load("trip_updates.json")}
    snap = build_snapshot(feeds, repo, None, NOW)

    def vehicle_ids(feed):
        return {e["vehicle"].get("vehicle", {}).get("id") or e["vehicle"].get("trip", {}).get("tripId", "")
                for e in feed.entities if "position" in e.get("vehicle", {})}

    for src in ("LD", "CER"):
        ids = vehicle_ids(feeds[f"{src}_vp"])
        assert len(ids) > 50
        assert {t.id for t in snap.trains.values() if t.source == src} == {f"{src}:{i}" for i in ids}
    assert all(-90 <= t.lat <= 90 for t in snap.trains.values())
    assert any(t.anden for t in snap.trains.values() if t.source == "CER")
