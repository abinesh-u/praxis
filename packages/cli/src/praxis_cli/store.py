"""Backward-compatible adapter unifying CLI storage on SQLiteUnitOfWork.

Eliminates the bespoke JSON file persistence engine in favor of the hardened
SQLite persistence engine from praxis_core.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from praxis_core.persistence.sqlite import (
    PersistenceConfigurationError,
    SQLiteApprovalRepository,
    SQLiteAttemptRepository,
    SQLiteAuditSink,
    SQLiteCommitmentRepository,
    SQLiteTaskRepository,
    SQLiteUnitOfWork,
)

# Re-export repository classes for backward compatibility
JsonTaskRepository = SQLiteTaskRepository
JsonCommitmentRepository = SQLiteCommitmentRepository
JsonApprovalRepository = SQLiteApprovalRepository
JsonAttemptRepository = SQLiteAttemptRepository
JsonAuditSink = SQLiteAuditSink


class StorageError(Exception):
    """Base exception for CLI storage failures."""


class StorageLockTimeoutError(StorageError):
    """Raised when the exclusive lock cannot be acquired within timeout."""


class CorruptStorageError(StorageError):
    """Raised when the storage file exists but cannot be deserialized or validated."""


class TransactionError(StorageError):
    """Raised when transactional operations are attempted outside an active transaction."""


class JsonFileUnitOfWork(SQLiteUnitOfWork):
    """Unified UnitOfWork for CLI, backed by SQLite with full ACID semantics."""

    def __init__(self, store_path: Path | str, lock_timeout_seconds: float = 5.0) -> None:
        p = Path(store_path)
        self.store_path = p
        self.lock_path = p.with_suffix(".lock")
        self._lock_timeout_seconds = lock_timeout_seconds

        db_path = p.with_name("praxis.db") if p.suffix == ".json" else p

        busy_timeout_ms = max(50, int(lock_timeout_seconds * 1000))
        super().__init__(
            database_url=f"sqlite:///{db_path}",
            busy_timeout_ms=busy_timeout_ms,
        )

    async def commit(self) -> None:
        if self._connection is None:
            raise TransactionError("Cannot commit outside an active transaction.")
        await super().commit()

    async def __aenter__(self) -> JsonFileUnitOfWork:
        if self.store_path.suffix == ".json" and self.store_path.exists():
            content = self.store_path.read_text(encoding="utf-8").strip()
            if content:
                try:
                    data = json.loads(content)
                    if not isinstance(data, dict):
                        raise CorruptStorageError("Storage root must be a JSON object.")
                except json.JSONDecodeError as err:
                    raise CorruptStorageError(f"Storage file corrupted: {err}") from err
            from praxis_cli.migration import JsonStoreMigrator

            JsonStoreMigrator.migrate_sync(self.store_path, self.database_url)

        try:
            await super().__aenter__()
        except (sqlite3.OperationalError, PersistenceConfigurationError) as exc:
            raise StorageLockTimeoutError(f"Database locked by another process: {exc}") from exc
        return self
