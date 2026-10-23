"""Integration tests for praxis doctor and status commands."""

import asyncio
from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.common import TaskStatus
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from typer.testing import CliRunner

runner = CliRunner()


def test_doctor_diagnostics_and_orphan_reconciliation(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Orphaned Task", status=TaskStatus.IN_PROGRESS)
    action = task.add_next_action("Some interrupted step")

    # Seed an orphaned running attempt
    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            attempt = ExecutionAttempt(
                owner_id="custom",
                task_id=task.id,
                action_id=action.id,
                idempotency_key="attempt-test-orphan",
                status="running",
            )
            await uow.attempts.save(attempt)
            await uow.commit()

    asyncio.run(_seed())

    # Run doctor
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "Praxis Doctor" in res.stdout
    assert "Reconciled 1 interrupted running attempt(s) to 'outcome_unknown'" in res.stdout
    assert "All diagnostic checks passed" in res.stdout

    # Verify attempt is now outcome_unknown and task is failed with recovery advice
    async def _check():
        async with uow:
            t = await uow.tasks.get_for_owner(task.id, "custom")
            assert t.status == TaskStatus.FAILED
            assert "outcome unknown" in t.failure_reason.lower()
            attempts = await uow.attempts.list_for_task(task.id, "custom")
            assert attempts[0].status == "outcome_unknown"

    asyncio.run(_check())


def test_status_command(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)

    async def _seed():
        async with uow:
            t = Task(owner_id="custom", title="Active Item", status=TaskStatus.IN_PROGRESS)
            await uow.tasks.save(t)
            await uow.commit()

    asyncio.run(_seed())

    res = runner.invoke(app, ["status"])
    assert res.exit_code == 0
    assert "Praxis Status" in res.stdout
    assert "Active Tasks:" in res.stdout
    assert "In Progress:" in res.stdout
