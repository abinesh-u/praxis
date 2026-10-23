"""Integration coverage for the API SQLite persistence adapter."""

import pytest
from praxis_api.persistence import SQLiteUnitOfWork, sqlite_path_from_url
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.common import ActionRiskLevel, TaskStatus
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from praxis_core.errors import ConcurrencyConflictError


def _database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'praxis.db'}"


@pytest.mark.anyio
async def test_entities_and_audit_events_survive_new_uow_instances(tmp_path):
    database_url = _database_url(tmp_path)
    task = Task(owner_id="owner-a", title="Submit report")
    action = task.add_next_action("Open the report")
    approval, _ = ApprovalRequest.create(
        owner_id="owner-a",
        task_id=task.id,
        action=ActionSpecification(tool_name="workspace_fs.write_file", task_id=task.id),
        risk_level=ActionRiskLevel.CONSEQUENTIAL,
        justification="Writes a report",
    )
    attempt = ExecutionAttempt(
        owner_id="owner-a",
        task_id=task.id,
        action_id=action.id,
        idempotency_key="submit-report-1",
    )

    async with SQLiteUnitOfWork(database_url) as uow:
        await uow.tasks.save(task)
        await uow.approvals.save(approval)
        await uow.attempts.save(attempt)
        uow.track_task(task)
        await uow.commit()

    async with SQLiteUnitOfWork(database_url) as uow:
        loaded = await uow.tasks.get_for_owner(task.id, "owner-a")
        assert loaded is not None
        assert loaded.next_actions[0].description == "Open the report"
        assert await uow.tasks.get_for_owner(task.id, "another-owner") is None
        assert (await uow.approvals.list_pending("owner-a"))[0].id == approval.id
        assert await uow.attempts.find_by_idempotency_key("submit-report-1", "owner-a") == attempt
        events = await uow.audit_sink.list_for_aggregate(task.id)
        assert [event.event_type for event in events] == ["task.created"]


@pytest.mark.anyio
async def test_commitment_idempotency_rollback_and_optimistic_conflict(tmp_path):
    database_url = _database_url(tmp_path)
    task = Task(owner_id="owner-a", title="Reconcile account")

    async with SQLiteUnitOfWork(database_url) as uow:
        await uow.tasks.save(task)
        await uow.commit()

    async with SQLiteUnitOfWork(database_url) as first:
        current = await first.tasks.get(task.id)
        assert current is not None
        current.start()
        await first.tasks.save(current, expected_version=1)
        await first.commit()

    async with SQLiteUnitOfWork(database_url) as second:
        stale = task.model_copy(deep=True)
        stale.cancel()
        with pytest.raises(ConcurrencyConflictError):
            await second.tasks.save(stale, expected_version=1)

    async with SQLiteUnitOfWork(database_url) as uow:
        stored = await uow.tasks.get(task.id)
        assert stored is not None and stored.status == TaskStatus.IN_PROGRESS


def test_sqlite_url_parsing_is_explicit():
    assert sqlite_path_from_url("sqlite:///:memory:") == ":memory:"
    assert sqlite_path_from_url("sqlite:////tmp/praxis.db") == "/tmp/praxis.db"
    with pytest.raises(ValueError, match="SQLite"):
        sqlite_path_from_url("postgresql://localhost/praxis")
