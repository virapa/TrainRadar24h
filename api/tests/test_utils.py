from datetime import date

from app.geo import bearing, haversine_m
from app.timeutil import hhmm, service_midnight


def test_service_midnight_and_hhmm():
    base = service_midnight(date(2026, 11, 11))
    assert hhmm(base + 11 * 3600 + 20 * 60) == "11:20"
    assert hhmm(base + 25 * 3600) == "01:00"  # pasa de medianoche


def test_haversine_and_bearing():
    assert 8300 < haversine_m(41.0, -2.0, 41.0, -1.9) < 8500
    assert abs(bearing(41.0, -2.0, 41.0, -1.9) - 90) < 1
    assert abs(bearing(41.0, -2.0, 42.0, -2.0) - 0) < 1
