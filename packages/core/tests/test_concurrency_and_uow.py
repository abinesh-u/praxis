"""Unit tests verifying optimistic concurrency versioning, Unit of Work, and Clock ports."""

from datetime import UTC, datetime, timedelta

import pytest
from praxis_core.entities.task import Task
from praxis_core.errors import ConcurrencyConflictError
from praxis_core.ports.clock import FrozenClock, SystemClock
from praxis_core.ports.task_repository import InMemoryTaskRepository
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork


class TestOptimisticConcurrency:
    """Verifies version check protection against concurrent modification."""

    @pytest.mark.anyio
    async def test_optimistic_concurrency_success_and_conflict(self):
        repo = InMemoryTaskRepository()
        task = Task(owner_id="user_1", title="Concurrent Task")
        assert task.version == 1

        # Save initial version
        await repo.save(task, expected_version=None)

        # Worker A reads task
        worker_a_task = await repo.get(task.id)
        assert worker_a_task is not None
        assert worker_a_task.version == 1

        # Worker B modifies task in storage
        task.start()
        assert task.version == 2
        await repo.save(task, expected_version=1)

        # Worker A attempts to save based on stale version 1
        worker_a_task.cancel()  # bumps version from 1 to 2 locally
        with pytest.raises(ConcurrencyConflictError) as exc_info:
            await repo.save(worker_a_task, expected_version=1)

        assert exc_info.value.expected_version == 1
        assert exc_info.value.actual_version == 2


class TestUnitOfWorkAndAuditDispatch:
    """Verifies that UoW atomically persists changes and dispatches aggregate domain events."""

    @pytest.mark.anyio
    async def test_uow_commit_flushes_domain_events_to_audit_sink(self):
        uow = InMemoryUnitOfWork()

        async with uow:
            task = Task(owner_id="user_1", title="Tracked Task")
            uow.track_task(task)

            task.start()
            task.defer(until=datetime.now(UTC) + timedelta(days=1), reason="Postponed")
            await uow.tasks.save(task)
            await uow.commit()

        # Audit sink must contain the emitted events
        audit_events = uow.audit_sink.get_events(aggregate_id=task.id)
        assert len(audit_events) >= 3  # TaskCreated, TaskStatusChanged (start), TaskDeferred

        event_types = [e.event_type for e in audit_events]
        assert "task.created" in event_types
        assert "task.status_changed" in event_types
        assert "task.deferred" in event_types

        # Aggregate event queue should be drained
        assert len(task.collect_events()) == 0

    @pytest.mark.anyio
    async def test_uow_rollback_on_exception(self):
        uow = InMemoryUnitOfWork()

        with pytest.raises(RuntimeError):
            async with uow:
                task = Task(owner_id="user_1", title="Failing Task")
                uow.track_task(task)
                task.start()
                raise RuntimeError("Simulated failure")

        # Events were not dispatched to audit sink
        assert len(uow.audit_sink.get_events()) == 0


class TestClockPort:
    """Verifies time abstraction and frozen clock behaviors."""

    def test_system_clock_returns_utc_datetime(self):
        clock = SystemClock()
        now = clock.now()
        assert now.tzinfo is not None
        assert now.tzinfo == UTC

    def test_frozen_clock_advance_and_set(self):
        base_time = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
        clock = FrozenClock(base_time)
        assert clock.now() == base_time

        # Advance by 30 minutes
        clock.advance(timedelta(minutes=30))
        assert clock.now() == datetime(2026, 10, 22, 12, 30, 0, tzinfo=UTC)

        # Set explicitly
        new_time = datetime(2026, 10, 25, 9, 0, 0, tzinfo=UTC)
        clock.set_time(new_time)
        assert clock.now() == new_time
