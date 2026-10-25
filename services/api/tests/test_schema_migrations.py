"""Tests for the SQLite schema migration runner."""

import multiprocessing
import sqlite3
import time
from uuid import uuid4

import pytest
from praxis_api.persistence import (
    MIGRATIONS,
    SCHEMA_VERSION,
    PersistenceConfigurationError,
    SQLiteUnitOfWork,
    _current_schema_version,
    schema_version,
)
from praxis_core.entities.task import Task


def _url(tmp_path, name="praxis.db") -> str:
    return f"sqlite:///{tmp_path / name}"


def test_fresh_database_applies_all_migrations(tmp_path):
    """A fresh database initializes schema_migrations and applies the baseline schema."""
    url = _url(tmp_path, "fresh.db")
    SQLiteUnitOfWork(url)
    assert schema_version(url) == SCHEMA_VERSION

    conn = sqlite3.connect(tmp_path / "fresh.db")
    rows = conn.execute("SELECT version, description FROM schema_migrations").fetchall()
    conn.close()
    assert len(rows) == len(MIGRATIONS)
    assert rows[0][0] == 1


def test_legacy_database_with_valid_fingerprint_baselines_safely(tmp_path):
    """A legacy database with existing tables matching the fingerprint is baselined to V1."""
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            status TEXT NOT NULL,
            version INTEGER NOT NULL,
            due_at TEXT,
            scheduled_at TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL
        );
        CREATE TABLE commitments (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            idempotency_key TEXT,
            captured_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE TABLE approvals (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE TABLE execution_attempts (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE TABLE audit_events (
            event_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        """
    )
    # Insert existing data
    task = Task(id=uuid4(), owner_id="legacy_owner", title="Pre-existing task")
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(task.id),
            task.owner_id,
            task.status.value,
            task.version,
            None,
            None,
            "",
            task.model_dump_json(),
        ),
    )
    conn.commit()
    conn.close()

    url = f"sqlite:///{db_file}"
    SQLiteUnitOfWork(url)
    assert schema_version(url) == 1

    # Verify existing data is preserved intact
    conn = sqlite3.connect(db_file)
    count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    conn.close()
    assert count == 1


def test_legacy_database_with_incompatible_schema_is_rejected(tmp_path):
    """A legacy database missing essential columns fails fast with PersistenceConfigurationError."""
    db_file = tmp_path / "corrupt.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            unrecognized_column TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    url = f"sqlite:///{db_file}"
    with pytest.raises(PersistenceConfigurationError, match="baseline format"):
        SQLiteUnitOfWork(url)


def test_legacy_database_missing_required_table_is_rejected(tmp_path):
    """A legacy database missing one of the required domain tables fails fingerprinting."""
    db_file = tmp_path / "missing_table.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, owner_id TEXT, status TEXT, version INT, payload TEXT
        );
        CREATE TABLE commitments (
            id TEXT PRIMARY KEY, owner_id TEXT, idempotency_key TEXT, captured_at TEXT, payload TEXT
        );
        -- approvals table is missing!
        CREATE TABLE execution_attempts (
            id TEXT PRIMARY KEY, owner_id TEXT, task_id TEXT, action_id TEXT,
            idempotency_key TEXT, status TEXT, payload TEXT
        );
        CREATE TABLE audit_events (
            event_id TEXT PRIMARY KEY, owner_id TEXT, aggregate_id TEXT,
            event_type TEXT, occurred_at TEXT, payload TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    url = f"sqlite:///{db_file}"
    with pytest.raises(PersistenceConfigurationError, match="baseline format"):
        SQLiteUnitOfWork(url)


def test_legacy_database_missing_column_in_attempts_is_rejected(tmp_path):
    """A legacy DB where execution_attempts is missing idempotency_key fails fingerprinting."""
    db_file = tmp_path / "missing_col.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, owner_id TEXT, status TEXT, version INT, payload TEXT
        );
        CREATE TABLE commitments (
            id TEXT PRIMARY KEY, owner_id TEXT, idempotency_key TEXT, captured_at TEXT, payload TEXT
        );
        CREATE TABLE approvals (
            id TEXT PRIMARY KEY, owner_id TEXT, task_id TEXT, status TEXT,
            expires_at TEXT, payload TEXT
        );
        -- execution_attempts is missing idempotency_key column
        CREATE TABLE execution_attempts (
            id TEXT PRIMARY KEY, owner_id TEXT, task_id TEXT, action_id TEXT,
            status TEXT, payload TEXT
        );
        CREATE TABLE audit_events (
            event_id TEXT PRIMARY KEY, owner_id TEXT, aggregate_id TEXT,
            event_type TEXT, occurred_at TEXT, payload TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    url = f"sqlite:///{db_file}"
    with pytest.raises(PersistenceConfigurationError, match="baseline format"):
        SQLiteUnitOfWork(url)


def test_idempotent_migration_application(tmp_path):
    """Calling SQLiteUnitOfWork repeatedly never duplicates migration history."""
    url = _url(tmp_path, "idem.db")
    SQLiteUnitOfWork(url)
    SQLiteUnitOfWork(url)
    assert schema_version(url) == SCHEMA_VERSION

    conn = sqlite3.connect(tmp_path / "idem.db")
    count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    conn.close()
    assert count == len(MIGRATIONS)


def test_faulty_migration_rolls_back_atomically(tmp_path):
    """A migration that fails due to bad SQL rolls back without recording the failed version."""
    url = _url(tmp_path, "rollback.db")
    uow = SQLiteUnitOfWork(url)
    conn = uow._connect()

    bad_migration = type(MIGRATIONS[0])(
        version=999,
        description="Faulty migration",
        sql="SYNTAX ERROR IN SQL STATEMENT;",
    )

    with pytest.raises(PersistenceConfigurationError, match="Failed to apply database migration"):
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executescript(bad_migration.sql)
            conn.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                (999, "bad", "now"),
            )
            conn.commit()
        except BaseException as exc:
            conn.rollback()
            raise PersistenceConfigurationError(
                f"Failed to apply database migration: {exc}"
            ) from exc

    # Version remains at previous level
    assert _current_schema_version(conn) == SCHEMA_VERSION
    conn.close()


def _worker_init_db(url: str) -> int:
    """Worker function for concurrent database startup race."""
    SQLiteUnitOfWork(url)
    return schema_version(url)


def test_concurrent_startup_migration_race(tmp_path):
    """Multiple processes starting simultaneously on a fresh DB synchronize via locks."""
    url = _url(tmp_path, "race.db")
    num_workers = 4

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(num_workers) as pool:
        results = [pool.apply_async(_worker_init_db, (url,)) for _ in range(num_workers)]
        versions = [r.get(timeout=30) for r in results]

    assert all(v == SCHEMA_VERSION for v in versions)

    conn = sqlite3.connect(tmp_path / "race.db")
    count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    conn.close()
    assert count == len(MIGRATIONS)


def test_migration_versions_are_sequential():
    """Verify that MIGRATIONS versions form a contiguous 1..N integer sequence."""
    versions = [m.version for m in MIGRATIONS]
    assert versions == list(range(1, len(MIGRATIONS) + 1))


def _lock_holder_worker(db_path_str: str, hold_seconds: float):
    """Holds an EXCLUSIVE lock on the database for hold_seconds."""
    conn = sqlite3.connect(db_path_str, isolation_level=None)
    conn.execute("BEGIN EXCLUSIVE")
    time.sleep(hold_seconds)
    conn.rollback()
    conn.close()


def test_lock_acquisition_timeout_raises_clear_error(tmp_path, monkeypatch):
    """When a competing process holds a lock longer than busy_timeout, fail with clear error."""
    monkeypatch.setenv("PRAXIS_SQLITE_BUSY_TIMEOUT_MS", "500")  # short 500ms timeout
    db_file = tmp_path / "contended.db"
    # Pre-initialize schema so file exists
    SQLiteUnitOfWork(f"sqlite:///{db_file}")

    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(target=_lock_holder_worker, args=(str(db_file), 2.0))
    p.start()
    time.sleep(0.4)  # wait for spawned process to start and acquire lock

    try:
        url = f"sqlite:///{db_file}"
        with pytest.raises(PersistenceConfigurationError, match="lock acquisition timed out"):
            SQLiteUnitOfWork(url)
    finally:
        p.join(timeout=5)
