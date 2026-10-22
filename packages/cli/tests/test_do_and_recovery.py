"""Integration tests for praxis do, consequential approval gates, and crash recovery."""

import asyncio
from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.common import ActionRiskLevel, TaskStatus
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from typer.testing import CliRunner

runner = CliRunner()


def test_do_routine_action(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Read README", status=TaskStatus.PLANNED)
    task.add_next_action("Read line 1 of README.md", risk_level=ActionRiskLevel.READ_ONLY)

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

    asyncio.run(_seed())

    short_id = str(task.id).replace("-", "")[:8]
    res = runner.invoke(app, ["do", short_id])
    assert res.exit_code == 0
    assert "Action completed" in res.stdout


def test_do_consequential_action_halts_for_approval(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Docker Prune", status=TaskStatus.PLANNED)
    task.add_next_action(
        "Delete all unused docker volumes", risk_level=ActionRiskLevel.CONSEQUENTIAL
    )

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

    asyncio.run(_seed())

    short_id = str(task.id).replace("-", "")[:8]
    res = runner.invoke(app, ["do", short_id])
    assert res.exit_code == 0
    assert "CONSEQUENTIAL ACTION REQUIRES APPROVAL" in res.stdout
    assert "Delete all unused docker volumes" in res.stdout


def test_do_defense_against_blind_retry_on_unknown_outcome(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Critical Deploy", status=TaskStatus.IN_PROGRESS)
    action = task.add_next_action("Inspect configuration file")

    # Inject an attempt with outcome_unknown (interrupted run)
    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            attempt = ExecutionAttempt(
                owner_id="custom",
                task_id=task.id,
                action_id=action.id,
                idempotency_key="attempt-test-unknown",
                status="outcome_unknown",
                error_message="Process interrupted during execution",
            )
            await uow.attempts.save(attempt)
            await uow.commit()

    asyncio.run(_seed())

    short_id = str(task.id).replace("-", "")[:8]

    # Without --force-retry, execution MUST be blocked
    res_blocked = runner.invoke(app, ["do", short_id])
    assert res_blocked.exit_code == 1
    assert "outcome is UNKNOWN" in res_blocked.stdout
    assert "--force-retry" in res_blocked.stdout

    # With --force-retry, execution proceeds
    res_forced = runner.invoke(app, ["do", short_id, "--force-retry"])
    assert res_forced.exit_code == 0
    assert "Action completed" in res_forced.stdout
