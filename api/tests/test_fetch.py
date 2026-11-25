import asyncio

import httpx
from google.transit import gtfs_realtime_pb2

from app.realtime.fetch import FeedFetcher, decode_feed


def sample_pb() -> bytes:
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = 1794392678
    e = msg.entity.add()
    e.id = "VP_C5-35903"
    e.vehicle.trip.trip_id = "3014X35903C5"
    e.vehicle.position.latitude = 37.5
    e.vehicle.position.longitude = -5.9
    e.vehicle.current_status = gtfs_realtime_pb2.VehiclePosition.INCOMING_AT
    e.vehicle.stop_id = "51103"
    e.vehicle.vehicle.id = "35903"
    e.vehicle.vehicle.label = "C5-35903-PLATF.(3)"
    return msg.SerializeToString()


def test_decode_feed_matches_renfe_json_shape():
    f = decode_feed(sample_pb(), fetched_at=10.0)
    v = f.entities[0]["vehicle"]
    assert (f.timestamp, f.fetched_at, f.stale) == (1794392678, 10.0, False)
    assert v["trip"]["tripId"] == "3014X35903C5"
    assert v["currentStatus"] == "INCOMING_AT"
    assert v["stopId"] == "51103"
    assert v["vehicle"]["label"] == "C5-35903-PLATF.(3)"
    assert abs(v["position"]["latitude"] - 37.5) < 1e-6


def test_fetcher_keeps_last_good_feed_and_backs_off():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=sample_pb()) if calls["n"] == 1 else httpx.Response(500)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = FeedFetcher({"CER_vp": "https://example.test/vp.pb"}, client)
            first = await fetcher.fetch_all(now=100.0)
            second = await fetcher.fetch_all(now=115.0)   # falla: conserva el anterior, marcado stale
            third = await fetcher.fetch_all(now=120.0)    # dentro de la espera: no hace petición
            return first, second, third

    first, second, third = asyncio.run(run())
    assert first["CER_vp"].stale is False
    assert second["CER_vp"].stale is True and len(second["CER_vp"].entities) == 1
    assert third["CER_vp"].stale is True
    assert calls["n"] == 2


def test_fetcher_without_any_success_returns_no_feed():
    async def run():
        transport = httpx.MockTransport(lambda r: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            return await FeedFetcher({"LD_vp": "https://example.test/x.pb"}, client).fetch_all(now=1.0)

    assert asyncio.run(run()) == {}
