import os
from dataclasses import dataclass, field
from pathlib import Path

RT = "https://gtfsrt.renfe.com"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("DATA_DIR", "./data")))
    poll_seconds: int = 15
    gtfs_min_bytes: int = 100_000
    feed_urls: dict[str, str] = field(default_factory=lambda: {
        "LD_vp": f"{RT}/vehicle_positions_LD.pb",
        "LD_tu": f"{RT}/trip_updates_LD.pb",
        "CER_vp": f"{RT}/vehicle_positions.pb",
        "CER_tu": f"{RT}/trip_updates.pb",
    })
    gtfs_urls: dict[str, str] = field(default_factory=lambda: {
        "LD": "https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip",
        "CER": "https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip",
    })
    vapid_private_key: str = field(default_factory=lambda: os.environ.get("VAPID_PRIVATE_KEY", ""))
    vapid_public_key: str = field(default_factory=lambda: os.environ.get("VAPID_PUBLIC_KEY", ""))
    vapid_subject: str = field(default_factory=lambda: os.environ.get("VAPID_SUBJECT", ""))

    @property
    def gtfs_db(self) -> Path:
        return self.data_dir / "gtfs.db"

    @property
    def app_db(self) -> Path:
        return self.data_dir / "app.db"
