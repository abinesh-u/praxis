"""Operational SQLite backup and audit-retention helpers.

These helpers intentionally use SQLite's online backup API rather than copying
the database file while it may be in use. They are small deployment
primitives, not a replacement for a managed backup system.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from praxis_api.persistence import sqlite_path_from_url


def _disk_path(database_url: str) -> Path:
    path = sqlite_path_from_url(database_url)
    if path == ":memory:":
        raise ValueError("Operational SQLite commands require a file-backed database")
    return Path(path).expanduser()


def backup_sqlite(source_url: str, destination_url: str) -> Path:
    """Create a consistent SQLite backup and verify its integrity."""

    source = _disk_path(source_url)
    destination = _disk_path(destination_url)
    if source.resolve() == destination.resolve():
        raise ValueError("Backup destination must differ from the source database")
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(source) as source_connection,
        sqlite3.connect(destination) as destination_connection,
    ):
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError(f"SQLite backup integrity check failed: {result!r}")
    return destination


def audit_event_count(database_url: str) -> int:
    """Return the number of retained audit events."""

    path = _disk_path(database_url)
    with sqlite3.connect(path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])


def prune_audit_events(database_url: str, before: datetime, owner_id: str | None = None) -> int:
    """Delete audit events older than ``before`` and return the deleted count.

    Callers must choose the cutoff explicitly. This prevents an operational
    command from silently applying an undocumented retention period.
    """

    path = _disk_path(database_url)
    cutoff = before.isoformat()
    with sqlite3.connect(path) as connection:
        if owner_id is None:
            cursor = connection.execute("DELETE FROM audit_events WHERE occurred_at < ?", (cutoff,))
        else:
            cursor = connection.execute(
                "DELETE FROM audit_events WHERE occurred_at < ? AND owner_id = ?",
                (cutoff, owner_id),
            )
        connection.commit()
        return cursor.rowcount
