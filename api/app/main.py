import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI

from . import appdb
from .alerts.run import process
from .api import stations, trains, user
from .config import Settings
from .gtfs_static.loader import needs_refresh, refresh_gtfs
from .realtime.fetch import FeedFetcher
from .realtime.snapshot import build_snapshot
from .state import State

log = logging.getLogger(__name__)
GTFS_CHECK_SECONDS = 1800


async def tick(st: State, fetcher) -> None:
    """Un ciclo: descargar feeds, construir el snapshot y procesar avisos."""
    if not st.settings.gtfs_db.exists():
        return    # todavía se están descargando los horarios
    now = st.clock()
    feeds = await fetcher.fetch_all(now)
    snap = await asyncio.to_thread(build_snapshot, feeds, st.repo, st.snapshot, now)
    st.prev, st.snapshot = st.snapshot, snap
    await asyncio.to_thread(process, st)


async def poll_loop(st: State) -> None:
    async with httpx.AsyncClient(headers={"User-Agent": "TrainRadar24h"}) as client:
        fetcher = FeedFetcher(st.settings.feed_urls, client)
        while True:
            try:
                await tick(st, fetcher)
            except Exception:
                log.exception("Fallo en el ciclo de tiempo real")
            await asyncio.sleep(st.settings.poll_seconds)


async def gtfs_loop(st: State) -> None:
    while True:
        try:
            if needs_refresh(st.settings.gtfs_db, st.clock()):
                log.info("Actualizando horarios GTFS…")
                await asyncio.to_thread(refresh_gtfs, st.settings)
                st.repo.reload()
                log.info("Horarios GTFS actualizados")
        except Exception:
            log.exception("No se pudieron actualizar los horarios; se mantiene la versión anterior")
        await asyncio.sleep(GTFS_CHECK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = []
    if app.state.background:
        tasks = [asyncio.create_task(gtfs_loop(app.state.st)), asyncio.create_task(poll_loop(app.state.st))]
    yield
    for task in tasks:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app(settings: Settings | None = None, background: bool = True) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or Settings()
    appdb.init(settings.app_db)
    app = FastAPI(title="TrainRadar24h API", lifespan=lifespan)
    app.state.st = State(settings)
    app.state.background = background
    app.include_router(trains.router)
    app.include_router(stations.router)
    app.include_router(user.router)
    return app
