import io
import zipfile

from app.gtfs_static.normalize import iter_table, norm_text, parse_time
from tests.helpers import CER_FILES, LD_FILES, make_zip


def _zf(raw: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(raw))


def test_strips_padded_headers_and_values():
    rows = list(iter_table(_zf(make_zip(LD_FILES, "cp1252")), "calendar.txt"))
    assert rows == [{
        "service_id": "S1", "monday": "1", "tuesday": "1", "wednesday": "1", "thursday": "1",
        "friday": "1", "saturday": "1", "sunday": "1", "start_date": "20261101", "end_date": "20261231",
    }]


def test_decodes_cp1252_and_utf8():
    ld = list(iter_table(_zf(make_zip(LD_FILES, "cp1252")), "stops.txt"))
    cer = list(iter_table(_zf(make_zip(CER_FILES)), "stops.txt"))
    assert ld[1]["stop_name"] == "Madrid-Chamartín-Clara Campoamor"
    assert cer[0]["stop_name"] == "Príncipe Pío"


def test_utf8_bom_is_removed():
    rows = list(iter_table(_zf(make_zip({"a.txt": "﻿x,y\n1,2\n"})), "a.txt"))
    assert rows == [{"x": "1", "y": "2"}]


def test_missing_file_yields_nothing():
    assert list(iter_table(_zf(make_zip(CER_FILES)), "calendar_dates.txt")) == []


def test_parse_time():
    assert parse_time("10:00:00") == 36000
    assert parse_time("25:10:30") == 90630
    assert parse_time(" 7:05:00 ") == 25500
    assert parse_time("") is None
    assert parse_time(None) is None


def test_norm_text():
    assert norm_text("  Madrid-Chamartín ") == "madrid-chamartin"
