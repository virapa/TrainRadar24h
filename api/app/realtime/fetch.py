import asyncio
import logging
from dataclasses import replace

import httpx
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2

from .models import Feed

log = logging.getLogger(__name__)
MAX_BACKOFF_S = 120


def decode_feed(raw: bytes, fetched_at: float) -> Feed:
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(raw)
    d = MessageToDict(msg)
    return Feed(entities=d.get("entity", []), timestamp=int(d.get("header", {}).get("timestamp", 0)),
                fetched_at=fetched_at)


class FeedFetcher:
    """Descarga los feeds. Si uno falla conserva el último bueno (stale) y espera antes de reintentar."""

    def __init__(self, urls: dict[str, str], client: httpx.AsyncClient):
        self.urls = urls
        self.client = client
        self.last: dict[str, Feed] = {}
        self.fails: dict[str, int] = {}
        self.next_try: dict[str, float] = {}

    async def fetch_all(self, now: float) -> dict[str, Feed]:
        await asyncio.gather(*(self._one(key, url, now) for key, url in self.urls.items()))
        return dict(self.last)

    async def _one(self, key: str, url: str, now: float) -> None:
        if now < self.next_try.get(key, 0.0):
            return
        try:
            resp = await self.client.get(url, timeout=10)
            resp.raise_for_status()
            self.last[key] = decode_feed(resp.content, now)
            self.fails[key] = 0
        except Exception as exc:  # red, HTTP o protobuf corrupto: mismo tratamiento
            n = self.fails.get(key, 0) + 1
            self.fails[key] = n
            self.next_try[key] = now + min(MAX_BACKOFF_S, 15 * 2 ** (n - 1))
            log.warning("feed %s falló (%s); reintento en %ss", key, exc, int(self.next_try[key] - now))
            if key in self.last:
                self.last[key] = replace(self.last[key], stale=True)
