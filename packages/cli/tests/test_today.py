"""Integration tests for praxis today."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.common import DependencyType, Priority, TaskStatus
from praxis_core.entities.dependency import Dependency
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from typer.testing import CliRunner

runner = CliRunner()


def test_today_empty_agenda(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    res = runner.invoke(app, ["today"])
    assert res.exit_code == 0
    assert "No active tasks on your agenda" in res.stdout


def test_today_spotlight_and_queue(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)

    async def _seed():
        async with uow:
            t1 = Task(
                owner_id="custom",
                title="Crucial Presentation",
                priority=Priority.URGENT,
                due_date=datetime.now(UTC) + timedelta(hours=2),
                status=TaskStatus.IN_PROGRESS,
            )
            t1.add_next_action("Finalize slide 4 charts")
            await uow.tasks.save(t1)

            t2 = Task(
                owner_id="custom",
                title="Routine Email Clean",
                priority=Priority.ROUTINE,
                scheduled_date=datetime.now(UTC),
                status=TaskStatus.PLANNED,
            )
            t2.add_next_action("Archive newsletters")
            await uow.tasks.save(t2)

            await uow.commit()

    asyncio.run(_seed())

    res = runner.invoke(app, ["today"])
    assert res.exit_code == 0
    assert "RIGHT NOW" in res.stdout
    assert "Crucial Presentation" in res.stdout
    assert "Finalize slide 4 charts" in res.stdout
    assert "TODAY'S QUEUE" in res.stdout
    assert "Routine Email Clean" in res.stdout


def test_today_moves_unknown_attempt_to_recovery_queue(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))
    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Uncertain webhook", status=TaskStatus.IN_PROGRESS)
    action = task.add_next_action("Check provider status")

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.attempts.save(
                ExecutionAttempt(
                    owner_id="custom",
                    task_id=task.id,
                    action_id=action.id,
                    idempotency_key="unknown-1",
                    status="outcome_unknown",
                    error="Timeout after dispatch",
                )
            )
            await uow.commit()

    asyncio.run(_seed())
    res = runner.invoke(app, ["today"])
    assert res.exit_code == 0
    assert "Outcome unknown" in res.stdout
    assert "reconcile before retry" in res.stdout
    assert "Uncertain webhook" in res.stdout


def test_today_explains_approval_and_dependency_blockers(tmp_path: Path, monkeypatch):
    """Waiting work remains visible with an actionable reason, not silently omitted."""
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))
    uow = JsonFileUnitOfWork(store_file)

    prerequisite = Task(owner_id="custom", title="Upload source files", status=TaskStatus.PLANNED)
    blocked = Task(owner_id="custom", title="Submit the report", status=TaskStatus.PLANNED)
    blocked.dependencies.append(
        Dependency(
            task_id=blocked.id,
            depends_on_task_id=prerequisite.id,
            dependency_type=DependencyType.BLOCKS,
        )
    )
    approval = Task(
        owner_id="custom", title="Send external message", status=TaskStatus.AWAITING_APPROVAL
    )
    blocked.add_next_action("Draft report")
    approval.add_next_action("Send message")

    async def _seed():
        async with uow:
            await uow.tasks.save(prerequisite)
            await uow.tasks.save(blocked)
            await uow.tasks.save(approval)
            await uow.commit()

    asyncio.run(_seed())

    res = runner.invoke(app, ["today"])
    assert res.exit_code == 0
    assert "Submit the report" in res.stdout
    assert "Blocked by 1 prerequisite" in res.stdout
    assert "Send external message" in res.stdout
    assert "Waiting for user" in res.stdout


def test_today_marks_unknown_execution_as_recovery_work(tmp_path: Path, monkeypatch):
    """An uncertain dispatch is never presented as a ready action to retry."""
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))
    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Publish release", status=TaskStatus.IN_PROGRESS)
    action = task.add_next_action("Publish the release")
    attempt = ExecutionAttempt(
        owner_id="custom",
        task_id=task.id,
        action_id=action.id,
        idempotency_key="publish-1",
        status="outcome_unknown",
        provider_request_id="provider-op-1",
        error="Provider timed out after dispatch",
    )

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.attempts.save(attempt)
            await uow.commit()

    asyncio.run(_seed())

    res = runner.invoke(app, ["today"])
    assert res.exit_code == 0
    assert "Publish release" in res.stdout
    assert "Outcome unknown" in res.stdout
    assert "reconcile before retry" in res.stdout
