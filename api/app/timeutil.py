from datetime import date, datetime, time
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def service_midnight(d: date) -> float:
    """Timestamp de las 00:00 (hora de Madrid) de la fecha de servicio."""
    return datetime.combine(d, time(0), MADRID).timestamp()


def hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts, MADRID).strftime("%H:%M")


def madrid_date(ts: float) -> date:
    return datetime.fromtimestamp(ts, MADRID).date()
