"""SQLite WAL Vault for synth patches and polyrhythmic sequencer patterns."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterator

from .presets import factory_patches, factory_patterns

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS patches (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Custom',
    data_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS patterns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    data_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


def default_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "sonatarack"


class StudioStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or (default_data_dir() / "studio.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        if not self.list_patches():
            for p in factory_patches():
                self.save_patch(p)
        if not self.list_patterns():
            for pat in factory_patterns():
                self.save_pattern(pat)

    def save_patch(self, patch: dict[str, Any]) -> None:
        pid = str(patch["id"])
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO patches (id, name, category, data_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, category=excluded.category, data_json=excluded.data_json, updated_at=excluded.updated_at
                """,
                (pid, str(patch.get("name", pid)), str(patch.get("category", "Custom")), json.dumps(patch), time.time()),
            )
            conn.commit()

    def list_patches(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data_json FROM patches ORDER BY updated_at ASC").fetchall()
        return [json.loads(r["data_json"]) for r in rows]

    def get_patch(self, patch_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            r = conn.execute("SELECT data_json FROM patches WHERE id = ?", (patch_id,)).fetchone()
        return json.loads(r["data_json"]) if r else None

    def save_pattern(self, pattern: dict[str, Any]) -> None:
        pid = str(pattern["id"])
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO patterns (id, name, data_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, data_json=excluded.data_json, updated_at=excluded.updated_at
                """,
                (pid, str(pattern.get("name", pid)), json.dumps(pattern), time.time()),
            )
            conn.commit()

    def list_patterns(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data_json FROM patterns ORDER BY updated_at ASC").fetchall()
        return [json.loads(r["data_json"]) for r in rows]

    def get_pattern(self, pattern_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            r = conn.execute("SELECT data_json FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        return json.loads(r["data_json"]) if r else None
