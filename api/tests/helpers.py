import io
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

# Miércoles 11-nov-2026, 11:00 hora de Madrid
NOW = datetime(2026, 11, 11, 11, 0, tzinfo=ZoneInfo("Europe/Madrid")).timestamp()
PAD = " " * 40

LD_FILES = {
    "routes.txt": (
        f"route_id,agency_id,route_short_name,route_long_name,route_type,route_color,route_text_color{PAD}\n"
        f"R1,1071,AVE,,2,FF0000,{PAD}\n"
    ),
    "trips.txt": (
        f"route_id,service_id,trip_id,trip_headsign,trip_short_name,shape_id{PAD}\n"
        f"R1,S1,0330412026-11-11,,03304,{PAD}\n"
    ),
    "stops.txt": (
        f"stop_id,stop_name,stop_lat,stop_lon{PAD}\n"
        "60000,Madrid-Puerta de Atocha,40.4066,-3.6902\n"
        "17000,Madrid-Chamartín-Clara Campoamor,40.4712,-3.6830\n"
        "04040,Zaragoza Delicias,41.6587,-0.9113\n"
        f"71801,Barcelona-Sants,41.3790,2.1400{PAD}\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "0330412026-11-11,10:00:00,10:00:00,60000,1\n"
        "0330412026-11-11,11:20:00,11:22:00,04040,2\n"
        "0330412026-11-11,12:45:00,12:45:00,71801,3\n"
    ),
    "calendar.txt": (
        f"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date{PAD}\n"
        f"S1,1,1,1,1,1,1,1,20261101,20261231{PAD}\n"
    ),
    "calendar_dates.txt": "service_id,date,exception_type\nS1,20261225,2\n",
}

CER_FILES = {
    "routes.txt": (
        "route_id,route_short_name,route_long_name,route_type,route_color\n"
        "10T0001C1  ,C1  ,Principe Pio -Aeropuerto-T4 ,2,75B6E0\n"
    ),
    "trips.txt": (
        "route_id,service_id,trip_id,trip_headsign,shape_id\n"
        "10T0001C1,1014X,1014X19799C1,,10_C1\n"
    ),
    "stops.txt": (
        "stop_id,stop_name,stop_lat,stop_lon\n"
        "18002,Príncipe Pío,40.4210,-3.7200\n"
        "18000,Madrid-Atocha Cercanías,40.4065,-3.6895\n"
        "04040,Zaragoza Delicias,41.6586576,-0.9112693\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "1014X19799C1,10:00:00,10:00:00,18002,1\n"
        "1014X19799C1,10:10:00,10:10:00,18000,2\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "1014X,0,0,1,0,0,0,0,20261111,20261111\n"
    ),
    "shapes.txt": (
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
        "10_C1,40.4210,-3.7200,1\n"
        "10_C1,40.4065,-3.6895,2\n"
    ),
}


def make_zip(files: dict[str, str], encoding: str = "utf-8") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text.encode(encoding))
    return buf.getvalue()


def gtfs_sources() -> dict[str, bytes]:
    """LD en cp1252 (como el real) y CER en UTF-8."""
    return {"LD": make_zip(LD_FILES, "cp1252"), "CER": make_zip(CER_FILES)}
