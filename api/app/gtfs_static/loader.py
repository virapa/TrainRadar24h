import io
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx

from ..config import Settings
from ..timeutil import MADRID, madrid_date
from .store import build_gtfs_db

REQUIRED = ("trips.txt", "stops.txt", "stop_times.txt", "routes.txt")
REFRESH_FROM_HOUR = 3


def download(url: str) -> bytes:
    resp = httpx.get(url, timeout=180, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def validate(raw: bytes, min_bytes: int) -> None:
    if len(raw) < min_bytes:
        raise ValueError(f"GTFS demasiado pequeño ({len(raw)} bytes)")
    try:
        names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
    except zipfile.BadZipFile as exc:
        raise ValueError("El GTFS descargado no es un zip válido") from exc
    for name in REQUIRED:
        if name not in names:
            raise ValueError(f"Al GTFS le falta {name}")


def refresh_gtfs(settings: Settings, download: Callable[[str], bytes] = download) -> None:
    """Descarga y valida los dos zips y reconstruye gtfs.db. Si algo falla, la base anterior queda intacta."""
    sources = {}
    for source, url in settings.gtfs_urls.items():
        raw = download(url)
        validate(raw, settings.gtfs_min_bytes)
        sources[source] = raw
    build_gtfs_db(settings.gtfs_db, sources)


def needs_refresh(path: Path, now: float) -> bool:
    """True si no hay base, o si es de un día anterior y ya son las 03:00 (hora de Madrid)."""
    if not path.exists():
        return True
    is_old = madrid_date(path.stat().st_mtime) < madrid_date(now)
    return is_old and datetime.fromtimestamp(now, MADRID).hour >= REFRESH_FROM_HOUR
