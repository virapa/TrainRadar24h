from app.realtime.models import Snapshot, Train


def make_train(**kw) -> Train:
    base = dict(id="LD:03304", source="LD", trip_id="T", fecha="2026-11-11", numero="03304",
                servicio="AVE", linea=None, color="#FF0000", lat=41.0, lon=-2.0, rumbo=None,
                estado="IN_TRANSIT_TO", origen=None, destino=None, proxima_parada=None,
                retraso_min=None, anden=None, progreso=None, casado_con_horario=False,
                cancelado=False, ts=0, paradas=[], shape_id="")
    return Train(**{**base, **kw})


def test_light_has_only_map_fields():
    assert set(make_train().light()) == {
        "id", "numero", "servicio", "linea", "color", "lat", "lon", "rumbo", "retraso_min", "estado"}


def test_empty_snapshot_and_by_trip():
    assert Snapshot.empty().trains == {}
    snap = Snapshot({"LD:03304": make_train()}, 0.0, {}, "x")
    assert snap.by_trip[("LD", "T")].id == "LD:03304"
