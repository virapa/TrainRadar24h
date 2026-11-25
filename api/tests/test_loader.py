import os

import pytest

from app.config import Settings
from app.gtfs_static.loader import needs_refresh, refresh_gtfs, validate
from app.gtfs_static.repo import GtfsRepo
from tests.helpers import NOW, gtfs_sources, make_zip


def test_validate():
    validate(gtfs_sources()["LD"], min_bytes=0)
    with pytest.raises(ValueError, match="pequeño"):
        validate(gtfs_sources()["LD"], min_bytes=10_000_000)
    with pytest.raises(ValueError, match="trips.txt"):
        validate(make_zip({"stops.txt": "stop_id\n"}), min_bytes=0)
    with pytest.raises(ValueError, match="zip"):
        validate(b"esto no es un zip", min_bytes=0)


def test_refresh_builds_db(tmp_path):
    settings = Settings(data_dir=tmp_path, gtfs_min_bytes=0)
    by_url = dict(zip(settings.gtfs_urls.values(), gtfs_sources().values()))
    refresh_gtfs(settings, download=by_url.__getitem__)
    assert GtfsRepo(settings.gtfs_db).trip("LD", "0330412026-11-11") is not None


def test_failed_refresh_keeps_previous_db(tmp_path):
    settings = Settings(data_dir=tmp_path, gtfs_min_bytes=0)
    by_url = dict(zip(settings.gtfs_urls.values(), gtfs_sources().values()))
    refresh_gtfs(settings, download=by_url.__getitem__)
    with pytest.raises(ValueError):
        refresh_gtfs(settings, download=lambda url: b"corrupto")
    assert GtfsRepo(settings.gtfs_db).trip("LD", "0330412026-11-11") is not None


def test_needs_refresh(tmp_path):
    path = tmp_path / "gtfs.db"
    assert needs_refresh(path, NOW) is True                       # no existe
    path.write_bytes(b"x")
    os.utime(path, (NOW - 3600, NOW - 3600))
    assert needs_refresh(path, NOW) is False                      # es de hoy
    os.utime(path, (NOW - 86400, NOW - 86400))
    assert needs_refresh(path, NOW) is True                       # es de ayer y son las 11:00
    assert needs_refresh(path, NOW - 9 * 3600) is False           # 02:00: aún no toca
