from dataclasses import dataclass, field
from functools import cached_property

LIGHT_FIELDS = ("id", "numero", "servicio", "linea", "color", "lat", "lon", "rumbo", "retraso_min", "estado")


@dataclass
class Feed:
    """Un feed GTFS-RT ya decodificado: entidades con la forma del JSON de Renfe."""
    entities: list[dict]
    timestamp: int          # header.timestamp del feed
    fetched_at: float
    stale: bool = False     # True si la última descarga falló y este es un dato antiguo


@dataclass
class Train:
    id: str                 # "LD:03304" / "CER:35903"
    source: str             # "LD" | "CER"
    trip_id: str
    fecha: str              # fecha de servicio, YYYY-MM-DD
    numero: str
    servicio: str           # AVE, ALVIA, MD… o "CERCANIAS"
    linea: str | None       # C1, C5… solo Cercanías
    color: str              # "#RRGGBB"
    lat: float
    lon: float
    rumbo: int | None
    estado: str             # IN_TRANSIT_TO | INCOMING_AT | STOPPED_AT
    origen: str | None
    destino: str | None
    proxima_parada: dict | None   # {id, nombre, hora_prog, hora_est}
    retraso_min: int | None
    anden: str | None
    progreso: float | None
    casado_con_horario: bool
    cancelado: bool
    ts: int
    paradas: list[dict] = field(default_factory=list)
    # cada parada: {id, nombre, lat, lon, ts_prog, ts_est, hora_prog, hora_est, retraso_s,
    #               estado: pasada|proxima|pendiente|suprimida}
    shape_id: str = ""

    def light(self) -> dict:
        return {k: getattr(self, k) for k in LIGHT_FIELDS}


@dataclass
class Snapshot:
    trains: dict[str, Train]
    generated_at: float
    feeds: dict[str, dict]  # {"LD": {"edad_s": 12, "stale": False}, "CER": {...}}
    etag: str

    @classmethod
    def empty(cls) -> "Snapshot":
        return cls({}, 0.0, {}, "empty")

    @cached_property
    def by_trip(self) -> dict[tuple[str, str], Train]:
        return {(t.source, t.trip_id): t for t in self.trains.values()}
