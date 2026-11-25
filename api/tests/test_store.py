import sqlite3
from contextlib import closing

from app.gtfs_static.store import build_gtfs_db
from tests.helpers import gtfs_sources


def q(path, sql, *params):
    with closing(sqlite3.connect(path)) as con:
        return con.execute(sql, params).fetchall()


def test_tables_are_loaded(gtfs_db):
    assert q(gtfs_db, "SELECT COUNT(*) FROM trips") == [(2,)]
    assert q(gtfs_db, "SELECT short_name, color FROM routes WHERE source='CER'") == [("C1", "75B6E0")]
    assert q(gtfs_db, "SELECT arr, dep FROM stop_times WHERE trip_id='0330412026-11-11' AND seq=2") == [(40800, 40920)]
    assert q(gtfs_db, "SELECT days, start_date FROM calendar WHERE service_id='1014X'") == [("0010000", "20261111")]
    assert q(gtfs_db, "SELECT exception_type FROM calendar_dates") == [(2,)]
    assert q(gtfs_db, "SELECT COUNT(*) FROM shapes WHERE shape_id='10_C1'") == [(2,)]
    assert q(gtfs_db, "SELECT value IS NOT NULL FROM meta WHERE key='loaded_at'") == [(1,)]


def test_train_number(gtfs_db):
    assert q(gtfs_db, "SELECT numero FROM trips WHERE source='LD'") == [("03304",)]
    assert q(gtfs_db, "SELECT numero FROM trips WHERE source='CER'") == [("19799",)]


def test_stops_are_merged_without_duplicates(gtfs_db):
    assert q(gtfs_db, "SELECT COUNT(*) FROM stops") == [(6,)]
    assert q(gtfs_db, "SELECT name_norm FROM stops WHERE stop_id='17000'") == [("madrid-chamartin-clara campoamor",)]
    assert q(gtfs_db, "SELECT COUNT(*) FROM stops WHERE stop_id='04040'") == [(1,)]


def test_rebuild_replaces_previous_file(gtfs_db):
    build_gtfs_db(gtfs_db, gtfs_sources())
    assert q(gtfs_db, "SELECT COUNT(*) FROM trips") == [(2,)]
    assert not gtfs_db.with_suffix(".new").exists()
