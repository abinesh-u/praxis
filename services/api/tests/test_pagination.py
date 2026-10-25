"""Tests for bounded query pagination, tie-breaker stability, and dataset drift."""

from datetime import UTC, datetime, timedelta

import pytest
from praxis_api.persistence import SQLiteUnitOfWork
from praxis_core.entities.common import TaskStatus
from praxis_core.entities.task import Task


def _url(tmp_path, name="praxis.db") -> str:
    return f"sqlite:///{tmp_path / name}"


@pytest.mark.anyio
async def test_pagination_empty_partial_exact_and_over_limit(tmp_path):
    url = _url(tmp_path, "paged.db")
    async with SQLiteUnitOfWork(url) as uow:
        # Empty
        assert await uow.tasks.list_by_owner("paged_user", limit=10, offset=0) == []

        # Seed 25 tasks
        for i in range(25):
            await uow.tasks.save(Task(owner_id="paged_user", title=f"Task {i:02d}"))
        await uow.commit()

    async with SQLiteUnitOfWork(url) as uow:
        # Page 1 (exact 10)
        p1 = await uow.tasks.list_by_owner("paged_user", limit=10, offset=0)
        assert len(p1) == 10

        # Page 2 (exact 10)
        p2 = await uow.tasks.list_by_owner("paged_user", limit=10, offset=10)
        assert len(p2) == 10

        # Page 3 (partial 5)
        p3 = await uow.tasks.list_by_owner("paged_user", limit=10, offset=20)
        assert len(p3) == 5

        # Page 4 (over limit / empty)
        p4 = await uow.tasks.list_by_owner("paged_user", limit=10, offset=30)
        assert len(p4) == 0

        # No overlap across pages
        p1_ids = {t.id for t in p1}
        p2_ids = {t.id for t in p2}
        p3_ids = {t.id for t in p3}
        assert not (p1_ids & p2_ids)
        assert not (p2_ids & p3_ids)


@pytest.mark.anyio
async def test_tie_breaker_stability_with_identical_timestamps(tmp_path):
    """Tasks with identical created_at timestamps maintain deterministic ordering via id ASC."""
    url = _url(tmp_path, "tiebreaker.db")
    now = datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC)

    tasks: list[Task] = []
    async with SQLiteUnitOfWork(url) as uow:
        for _ in range(10):
            t = Task(owner_id="tie_user", title="Same timestamp", created_at=now)
            tasks.append(t)
            await uow.tasks.save(t)
        await uow.commit()

    expected_order = sorted([t.id for t in tasks], key=lambda tid: str(tid))

    async with SQLiteUnitOfWork(url) as uow:
        p1 = await uow.tasks.list_by_owner("tie_user", limit=5, offset=0)
        p2 = await uow.tasks.list_by_owner("tie_user", limit=5, offset=5)

    actual_order = [t.id for t in p1] + [t.id for t in p2]
    assert actual_order == expected_order


@pytest.mark.anyio
async def test_pagination_limits_and_offset_clamping(tmp_path):
    url = _url(tmp_path, "clamping.db")
    async with SQLiteUnitOfWork(url) as uow:
        for i in range(5):
            await uow.tasks.save(Task(owner_id="clamp_user", title=f"T{i}"))
        await uow.commit()

    async with SQLiteUnitOfWork(url) as uow:
        # Requesting limit > 1000 is clamped to 1000
        res = await uow.tasks.list_by_owner("clamp_user", limit=5000)
        assert len(res) == 5

        # Requesting limit < 1 is clamped to 1
        res_min = await uow.tasks.list_by_owner("clamp_user", limit=0)
        assert len(res_min) == 1

        # Negative offset is clamped to 0
        res_neg = await uow.tasks.list_by_owner("clamp_user", limit=10, offset=-5)
        assert len(res_neg) == 5


@pytest.mark.anyio
async def test_pagination_owner_isolation(tmp_path):
    url = _url(tmp_path, "iso.db")
    async with SQLiteUnitOfWork(url) as uow:
        await uow.tasks.save(Task(owner_id="alice", title="Alice Task"))
        await uow.tasks.save(Task(owner_id="bob", title="Bob Task"))
        await uow.commit()

    async with SQLiteUnitOfWork(url) as uow:
        alice_tasks = await uow.tasks.list_by_owner("alice")
        assert len(alice_tasks) == 1
        assert alice_tasks[0].title == "Alice Task"

        bob_tasks = await uow.tasks.list_by_owner("bob")
        assert len(bob_tasks) == 1
        assert bob_tasks[0].title == "Bob Task"


@pytest.mark.anyio
async def test_dataset_drift_between_page_fetches(tmp_path):
    """Verifies offset behavior when a new record is inserted between page 1 and page 2 fetches."""
    url = _url(tmp_path, "drift.db")
    base_time = datetime(2026, 10, 25, 10, 0, 0, tzinfo=UTC)

    async with SQLiteUnitOfWork(url) as uow:
        for i in range(10):
            t = Task(
                owner_id="drift_user",
                title=f"Task {i}",
                created_at=base_time + timedelta(minutes=i),
            )
            await uow.tasks.save(t)
        await uow.commit()

    async with SQLiteUnitOfWork(url) as uow:
        page_1 = await uow.tasks.list_by_owner("drift_user", limit=5, offset=0)
        assert len(page_1) == 5

    # Concurrently insert a new task with earlier timestamp (drift)
    async with SQLiteUnitOfWork(url) as uow:
        earlier_task = Task(
            owner_id="drift_user",
            title="Drift task",
            created_at=base_time - timedelta(minutes=5),
        )
        await uow.tasks.save(earlier_task)
        await uow.commit()

    async with SQLiteUnitOfWork(url) as uow:
        # Fetching page 2 with offset 5 cleanly returns 5 rows without error
        page_2 = await uow.tasks.list_by_owner("drift_user", limit=5, offset=5)
        assert len(page_2) == 5
        # The earliest task now pushed the previous index 4 item to index 5
        assert page_2[0].id == page_1[4].id


@pytest.mark.anyio
async def test_daily_agenda_completeness_unbounded(tmp_path):
    """list_active_for_today retrieves all active tasks without truncation."""
    url = _url(tmp_path, "agenda.db")
    today = datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC)

    async with SQLiteUnitOfWork(url) as uow:
        for i in range(50):
            t = Task(
                owner_id="agenda_user",
                title=f"Actionable {i}",
                scheduled_date=today,
                status=TaskStatus.PLANNED,
            )
            await uow.tasks.save(t)
        await uow.commit()

    async with SQLiteUnitOfWork(url) as uow:
        active = await uow.tasks.list_active_for_today(today, "agenda_user")
        assert len(active) == 50
