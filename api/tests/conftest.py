import pytest

from app.gtfs_static.store import build_gtfs_db
from tests.helpers import gtfs_sources


@pytest.fixture
def gtfs_db(tmp_path):
    path = tmp_path / "gtfs.db"
    build_gtfs_db(path, gtfs_sources())
    return path


from app.gtfs_static.repo import GtfsRepo


@pytest.fixture
def repo(gtfs_db):
    return GtfsRepo(gtfs_db)


from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.realtime.models import Feed
from app.realtime.snapshot import build_snapshot
from tests.helpers import NOW

LD_TRIP = "0330412026-11-11"


def sample_feeds() -> dict[str, Feed]:
    """Un AVE con 5 min de retraso camino de Zaragoza y un Cercanías sin casar."""
    def feed(entities):
        return Feed(entities=entities, timestamp=int(NOW), fetched_at=NOW)

    return {
        "LD_vp": feed([{"id": "VP_03304", "vehicle": {
            "trip": {"tripId": LD_TRIP}, "position": {"latitude": 41.0, "longitude": -2.0},
            "currentStatus": "IN_TRANSIT_TO", "stopId": "04040",
            "vehicle": {"id": "03304", "label": "03304"}}}]),
        "LD_tu": feed([{"id": "TU", "tripUpdate": {
            "trip": {"tripId": LD_TRIP},
            "stopTimeUpdate": [{"stopId": "04040", "arrival": {"delay": 300}}]}}]),
        "CER_vp": feed([{"id": "VP_C5", "vehicle": {
            "trip": {"tripId": "3014X35903C5"}, "position": {"latitude": 37.32, "longitude": -5.96},
            "currentStatus": "INCOMING_AT", "stopId": "51103",
            "vehicle": {"id": "35903", "label": "C5-35903-PLATF.(3)"}}}]),
    }


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path)
    build_gtfs_db(settings.gtfs_db, gtfs_sources())
    app = create_app(settings, background=False)
    st = app.state.st
    st.clock = lambda: NOW
    st.snapshot = build_snapshot(sample_feeds(), st.repo, None, NOW)
    return TestClient(app)
