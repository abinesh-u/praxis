"""Multi-process concurrency tests for JsonFileUnitOfWork with sidecar locking."""

import asyncio
import multiprocessing
from pathlib import Path
from uuid import uuid4

from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.task import Task


def _worker_add_tasks(store_path_str: str, worker_id: int, count: int) -> int:
    """Independent process worker that saves tasks through JsonFileUnitOfWork."""

    async def _async_run():
        store_path = Path(store_path_str)
        saved = 0
        for i in range(count):
            uow = JsonFileUnitOfWork(store_path, lock_timeout_seconds=10.0)
            async with uow:
                task = Task(
                    id=uuid4(),
                    owner_id="concurrency_owner",
                    title=f"Worker {worker_id} - Task {i}",
                )
                await uow.tasks.save(task)
                await uow.commit()
                saved += 1
        return saved

    return asyncio.run(_async_run())


def test_multiprocess_concurrency_zero_lost_updates(tmp_path: Path):
    """Multiple real OS processes write concurrently to the same store file.

    Verifies:
    1. Exclusive sidecar locking serializes all process writes.
    2. Atomic replacement and directory fsync prevent file corruption.
    3. Exactly (workers * count) tasks exist at the end (zero lost updates).
    """
    store_file = tmp_path / "profiles" / "concurrent" / "store.json"
    num_workers = 4
    tasks_per_worker = 5
    total_expected = num_workers * tasks_per_worker

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(num_workers) as pool:
        results = [
            pool.apply_async(
                _worker_add_tasks,
                (str(store_file), w_id, tasks_per_worker),
            )
            for w_id in range(num_workers)
        ]
        saved_counts = [r.get(timeout=30) for r in results]

    assert sum(saved_counts) == total_expected

    # Verify state in store
    async def _check_total():
        uow = JsonFileUnitOfWork(store_file)
        async with uow:
            tasks = await uow.tasks.list_by_owner("concurrency_owner")
            assert len(tasks) == total_expected

    asyncio.run(_check_total())
