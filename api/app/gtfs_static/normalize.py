import csv
import io
import unicodedata
import zipfile
from collections.abc import Iterator


def decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def iter_table(zf: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    """Filas de un CSV del zip, con cabeceras y valores sin espacios sobrantes."""
    if name not in zf.namelist():
        return
    reader = csv.reader(io.StringIO(decode(zf.read(name))))
    header = [h.strip() for h in next(reader, [])]
    for row in reader:
        if row:
            yield {h: v.strip() for h, v in zip(header, row)}


def parse_time(value: str | None) -> int | None:
    """'HH:MM:SS' → segundos desde medianoche (HH puede ser ≥ 24)."""
    if not value or not value.strip():
        return None
    h, m, s = value.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def norm_text(text: str) -> str:
    """Minúsculas y sin acentos, para buscar."""
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))
