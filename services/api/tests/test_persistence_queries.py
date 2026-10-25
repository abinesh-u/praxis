"""Tests for SQLite index query plans, multi-process concurrency, and permissions."""

import asyncio
import multiprocessing
import os
import stat
from uuid import uuid4

from praxis_api.persistence import SQLiteUnitOfWork
from praxis_core.entities.task import Task


def _url(tmp_path, name="praxis.db") -> str:
    return f"sqlite:///{tmp_path / name}"


def test_explain_query_plan_uses_expected_indexes(tmp_path):
    """Verify with EXPLAIN QUERY PLAN that queries use dedicated and expression indexes."""
    url = _url(tmp_path, "indexes.db")
    uow = SQLiteUnitOfWork(url)
    conn = uow._connect()

    # 1. find_by_commitment_id should use expression index tasks_owner_commitment_idx
    plan_commitment = conn.execute(
        "EXPLAIN QUERY PLAN SELECT payload FROM tasks WHERE owner_id = ? "
        "AND json_extract(payload, '$.commitment_id') = ?",
        ("owner-1", "some-uuid"),
    ).fetchall()
    plan_commitment_text = " ".join(r[3] for r in plan_commitment)
    assert "tasks_owner_commitment_idx" in plan_commitment_text

    # 2. count_by_status should use covering index tasks_owner_status_idx
    plan_status = conn.execute(
        "EXPLAIN QUERY PLAN SELECT status, COUNT(*) FROM tasks WHERE owner_id = ? GROUP BY status",
        ("owner-1",),
    ).fetchall()
    plan_status_text = " ".join(r[3] for r in plan_status)
    assert "tasks_owner_status_idx" in plan_status_text

    # 3. find_by_id_prefix should use index tasks_owner_id_idx
    plan_prefix = conn.execute(
        "EXPLAIN QUERY PLAN SELECT payload FROM tasks WHERE owner_id = ? "
        "AND id LIKE (? || '%') ORDER BY id ASC",
        ("owner-1", "abc"),
    ).fetchall()
    plan_prefix_text = " ".join(r[3] for r in plan_prefix)
    assert "tasks_owner_id_idx" in plan_prefix_text

    # 4. list_by_owner should use tasks_owner_created_idx
    plan_paged = conn.execute(
        "EXPLAIN QUERY PLAN SELECT payload FROM tasks WHERE owner_id = ? "
        "ORDER BY created_at ASC, id ASC LIMIT 10 OFFSET 0",
        ("owner-1",),
    ).fetchall()
    plan_paged_text = " ".join(r[3] for r in plan_paged)
    assert "tasks_owner_created_idx" in plan_paged_text

    conn.close()


def _worker_create_tasks(database_url: str, worker_id: int, count: int) -> int:
    """Worker process creating tasks through independent SQLiteUnitOfWork instances."""

    async def _run():
        saved = 0
        for i in range(count):
            async with SQLiteUnitOfWork(database_url) as uow:
                task = Task(
                    id=uuid4(),
                    owner_id="stress_owner",
                    title=f"Worker-{worker_id}-Task-{i}",
                )
                await uow.tasks.save(task)
                uow.track_task(task)
                await uow.commit()
                saved += 1
        return saved

    return asyncio.run(_run())


def test_concurrent_api_writes_zero_lost_updates(tmp_path):
    """Multiple real OS processes write concurrently to SQLite with zero lost updates."""
    url = _url(tmp_path, "concurrency.db")
    SQLiteUnitOfWork(url)  # Pre-initialize schema

    num_workers = 4
    tasks_per_worker = 10
    total_expected = num_workers * tasks_per_worker

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(num_workers) as pool:
        results = [
            pool.apply_async(_worker_create_tasks, (url, w, tasks_per_worker))
            for w in range(num_workers)
        ]
        saved_counts = [r.get(timeout=30) for r in results]

    assert sum(saved_counts) == total_expected

    async def _verify():
        async with SQLiteUnitOfWork(url) as uow:
            tasks = await uow.tasks.list_by_owner("stress_owner", limit=1000)
            assert len(tasks) == total_expected
            # Verify every individual task content and title was persisted without corruption
            saved_titles = {t.title for t in tasks}
            for w in range(num_workers):
                for i in range(tasks_per_worker):
                    assert f"Worker-{w}-Task-{i}" in saved_titles

    asyncio.run(_verify())


def _worker_attempt_dispatch(database_url: str, task_id_str: str, idempotency_key: str) -> str:
    """Worker process attempting to record an execution attempt with a shared idempotency key."""

    async def _run():
        task_id = __import__("uuid").UUID(task_id_str)
        attempt_id = uuid4()
        from praxis_core.entities.execution_attempt import ExecutionAttempt

        attempt = ExecutionAttempt(
            id=attempt_id,
            owner_id="dispatch_owner",
            task_id=task_id,
            action_id=uuid4(),
            idempotency_key=idempotency_key,
            status="running",
        )
        try:
            async with SQLiteUnitOfWork(database_url) as uow:
                existing = await uow.attempts.find_by_idempotency_key(
                    idempotency_key, "dispatch_owner"
                )
                if existing is not None:
                    return f"duplicate_found:{existing.id}"
                await uow.attempts.save(attempt)
                await uow.commit()
                return f"dispatched:{attempt_id}"
        except Exception as exc:
            return f"conflict:{type(exc).__name__}"

    return asyncio.run(_run())


def test_concurrent_duplicate_dispatch_prevention(tmp_path):
    """4 concurrent OS processes attempt dispatch with identical key; exactly 1 succeeds."""
    url = _url(tmp_path, "duplicate_prevention.db")
    SQLiteUnitOfWork(url)  # Pre-initialize schema

    task_id = str(uuid4())
    shared_key = "idempotent-dispatch-key-42"
    num_workers = 4

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(num_workers) as pool:
        results = [
            pool.apply_async(_worker_attempt_dispatch, (url, task_id, shared_key))
            for _ in range(num_workers)
        ]
        outcomes = [r.get(timeout=30) for r in results]

    # Verify that exactly ONE process was permitted to dispatch
    dispatched_count = sum(1 for o in outcomes if o.startswith("dispatched:"))
    assert dispatched_count == 1

    # Remaining processes either detected duplicate or encountered a transaction conflict
    non_dispatched_count = sum(
        1 for o in outcomes if o.startswith("duplicate_found:") or o.startswith("conflict:")
    )
    assert non_dispatched_count == num_workers - 1

    # In database, exactly one attempt exists with this idempotency key
    async def _verify_attempt():
        async with SQLiteUnitOfWork(url) as uow:
            attempt = await uow.attempts.find_by_idempotency_key(shared_key, "dispatch_owner")
            assert attempt is not None
            assert attempt.status == "running"

    asyncio.run(_verify_attempt())


def _worker_optimistic_conflict(database_url: str, task_id_str: str) -> str:
    """Worker process attempting optimistic update; returns 'ok' or 'conflict'."""

    async def _run():
        async with SQLiteUnitOfWork(database_url) as uow:
            task = await uow.tasks.get_for_owner(__import__("uuid").UUID(task_id_str), "opt_owner")
            if task is None:
                return "missing"
            try:
                task.start()
                await uow.tasks.save(task, expected_version=1)
                uow.track_task(task)
                await uow.commit()
                return "ok"
            except Exception:
                return "conflict"

    return asyncio.run(_run())


def test_optimistic_locking_under_process_contention(tmp_path):
    """When multiple processes attempt to advance the same version-1 task, exactly one succeeds."""
    url = _url(tmp_path, "optlock.db")
    task = Task(owner_id="opt_owner", title="Race target")

    async def _seed():
        async with SQLiteUnitOfWork(url) as uow:
            await uow.tasks.save(task)
            uow.track_task(task)
            await uow.commit()

    asyncio.run(_seed())

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(4) as pool:
        results = [
            pool.apply_async(_worker_optimistic_conflict, (url, str(task.id))) for _ in range(4)
        ]
        outcomes = [r.get(timeout=30) for r in results]

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == 3


def test_selective_file_and_directory_permissions(tmp_path):
    """Praxis applies 0o600 to database files and 0o700 to the application leaf dir."""
    nested_dir = tmp_path / "praxis_app_data"
    db_file = nested_dir / "secure.db"
    url = f"sqlite:///{db_file}"

    SQLiteUnitOfWork(url)

    # Check file permissions (0600)
    file_mode = stat.S_IMODE(os.stat(db_file).st_mode)
    assert file_mode == 0o600

    # Check directory permissions (0700)
    dir_mode = stat.S_IMODE(os.stat(nested_dir).st_mode)
    assert dir_mode == 0o700
