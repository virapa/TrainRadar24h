import json
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites(device_id TEXT, tipo TEXT, ref TEXT, avisos TEXT,
                                     PRIMARY KEY(device_id, tipo, ref));
CREATE TABLE IF NOT EXISTS push_subs(device_id TEXT PRIMARY KEY, sub TEXT);
CREATE TABLE IF NOT EXISTS notified(device_id TEXT, ref TEXT, fecha TEXT, tipo TEXT, valor TEXT,
                                    PRIMARY KEY(device_id, ref, fecha, tipo));
"""


def _run(path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    with closing(sqlite3.connect(path)) as con, con:   # 'con' como contexto hace commit
        return con.execute(sql, params).fetchall()


def init(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as con, con:
        con.executescript(SCHEMA)


def list_favorites(path: Path, device_id: str | None = None) -> list[dict]:
    sql, params = "SELECT device_id, tipo, ref, avisos FROM favorites", ()
    if device_id is not None:
        sql, params = sql + " WHERE device_id=?", (device_id,)
    return [{"device_id": d, "tipo": t, "ref": r, "avisos": json.loads(a)} for d, t, r, a in _run(path, sql, params)]


def put_favorite(path: Path, device_id: str, tipo: str, ref: str, avisos: dict) -> None:
    _run(path, "INSERT OR REPLACE INTO favorites VALUES(?,?,?,?)", (device_id, tipo, ref, json.dumps(avisos)))


def delete_favorite(path: Path, device_id: str, tipo: str, ref: str) -> None:
    _run(path, "DELETE FROM favorites WHERE device_id=? AND tipo=? AND ref=?", (device_id, tipo, ref))


def put_subscription(path: Path, device_id: str, sub: dict) -> None:
    _run(path, "INSERT OR REPLACE INTO push_subs VALUES(?,?)", (device_id, json.dumps(sub)))


def get_subscription(path: Path, device_id: str) -> dict | None:
    rows = _run(path, "SELECT sub FROM push_subs WHERE device_id=?", (device_id,))
    return json.loads(rows[0][0]) if rows else None


def delete_subscription(path: Path, device_id: str) -> None:
    _run(path, "DELETE FROM push_subs WHERE device_id=?", (device_id,))


def notified_map(path: Path) -> dict[tuple[str, str, str, str], str]:
    return {(d, r, f, t): v for d, r, f, t, v in
            _run(path, "SELECT device_id, ref, fecha, tipo, valor FROM notified")}


def set_notified(path: Path, device_id: str, ref: str, fecha: str, tipo: str, valor: str) -> None:
    _run(path, "INSERT OR REPLACE INTO notified VALUES(?,?,?,?,?)", (device_id, ref, fecha, tipo, valor))
