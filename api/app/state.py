import time
from collections.abc import Callable

from .config import Settings
from .gtfs_static.repo import GtfsRepo
from .realtime.models import Snapshot


class State:
    """Estado compartido del proceso: repositorio GTFS, snapshot actual y anterior, reloj."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = GtfsRepo(settings.gtfs_db)
        self.app_db = settings.app_db
        self.snapshot: Snapshot = Snapshot.empty()
        self.prev: Snapshot | None = None
        self.clock: Callable[[], float] = time.time
