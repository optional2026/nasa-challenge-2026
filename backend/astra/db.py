"""SQLite persistence layer: connections, schema creation, small helpers.

The schema is explicit relational DDL (see schema.sql). Every request/thread
uses its own connection; WAL mode allows the simulator and sync worker to
write while the API reads.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import config

SCHEMA_VERSION = "1"
_init_lock = threading.Lock()


# ------------------------------------------------------------------ time helpers
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """Canonical UTC timestamp string (sortable): 2026-11-14T10:30:00.000Z"""
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed; timestamps must be timezone-aware")
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def now_iso() -> str:
    return iso(utcnow())


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp that MUST carry a timezone."""
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    v = value.strip()
    if v.endswith("Z") or v.endswith("z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        raise ValueError("timestamp must include a timezone (e.g. 'Z' for UTC)")
    return dt.astimezone(timezone.utc)


def hours_ago(h: float) -> str:
    return iso(utcnow() - timedelta(hours=h))


# ------------------------------------------------------------------ ids / json
def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def loads(s: str | None, default: Any = None) -> Any:
    if s is None or s == "":
        return default
    return json.loads(s)


def sha256(obj: Any) -> str:
    return hashlib.sha256(dumps(obj).encode()).hexdigest()


# ------------------------------------------------------------------ connections
def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = Path(path or config.db_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30, check_same_thread=False, isolation_level=None)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT/ROLLBACK. Nested use joins the outer transaction."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    with _init_lock:
        sql = (Path(__file__).parent / "schema.sql").read_text()
        conn.executescript(sql)
        _migrate(conn)
        conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive, idempotent column migrations for databases created by earlier versions."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(astronauts)").fetchall()}
    if "crew" not in cols:
        conn.execute("ALTER TABLE astronauts ADD COLUMN crew TEXT NOT NULL DEFAULT 'Prime Crew'")


# ------------------------------------------------------------------ query helpers
def one(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> dict | None:
    return conn.execute(sql, tuple(params)).fetchone()


def all_(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> list[dict]:
    return conn.execute(sql, tuple(params)).fetchall()


def insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    cols = ",".join(row.keys())
    qs = ",".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", tuple(row.values()))


def update(conn: sqlite3.Connection, table: str, key: str, key_value: Any, changes: dict) -> None:
    sets = ",".join(f"{k}=?" for k in changes)
    conn.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", (*changes.values(), key_value))
