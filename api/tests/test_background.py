import asyncio

from app import appdb
from app.main import tick
from tests.conftest import sample_feeds
from tests.helpers import NOW


class FakeFetcher:
    async def fetch_all(self, now):
        return sample_feeds()


def test_tick_builds_snapshot_and_runs_alerts(client):
    st = client.app.state.st
    first = st.snapshot
    appdb.put_favorite(st.app_db, "device-0001", "tren", "03304", {"retraso": True})
    asyncio.run(tick(st, FakeFetcher()))
    assert st.prev is first and st.snapshot is not first
    assert set(st.snapshot.trains) == {"LD:03304", "CER:35903"}
    assert ("device-0001", "03304", "2026-11-11", "retraso") in appdb.notified_map(st.app_db)


def test_tick_waits_for_gtfs(client):
    st = client.app.state.st
    st.settings.gtfs_db.unlink()
    before = st.snapshot
    asyncio.run(tick(st, FakeFetcher()))
    assert st.snapshot is before
