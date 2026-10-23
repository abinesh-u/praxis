"""Integration tests for praxis show and praxis list."""

import asyncio
from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.common import TaskStatus
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from typer.testing import CliRunner

runner = CliRunner()


def test_list_and_show_commands(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(
        owner_id="custom", title="Detailed Inspection Task", description="Deep review required"
    )
    task.add_next_action("Inspect line 42")

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

    asyncio.run(_seed())

    short_id = str(task.id).replace("-", "")[:8]

    # Test list
    res_list = runner.invoke(app, ["list"])
    assert res_list.exit_code == 0
    assert "Detailed Inspection Task" in res_list.stdout

    # Test show
    res_show = runner.invoke(app, ["show", short_id])
    assert res_show.exit_code == 0
    assert f"Task {short_id}" in res_show.stdout
    assert "Deep review required" in res_show.stdout
    assert "Inspect line 42" in res_show.stdout


def test_show_includes_safe_attempt_recovery_metadata(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Reconcile deployment", status="in_progress")
    action = task.add_next_action("Check provider status")
    attempt = ExecutionAttempt(
        owner_id="custom",
        task_id=task.id,
        action_id=action.id,
        idempotency_key="safe-key",
        status="outcome_unknown",
        provider_request_id="provider-op-7",
        error="Provider timeout",
    )

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.attempts.save(attempt)
            await uow.commit()

    asyncio.run(_seed())
    res = runner.invoke(app, ["show", str(task.id).replace("-", "")[:8]])
    assert res.exit_code == 0
    assert "Outcome unknown" in res.stdout
    assert "provider-op-7" in res.stdout
    assert "Reconcile before retrying" in res.stdout
    # The idempotency key is sensitive operational metadata and is not rendered.
    assert "safe-key" not in res.stdout


def test_show_surfaces_attempt_recovery_metadata(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))
    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Reconcile provider result", status=TaskStatus.IN_PROGRESS)
    action = task.add_next_action("Check provider status")
    attempt = ExecutionAttempt(
        owner_id="custom",
        task_id=task.id,
        action_id=action.id,
        idempotency_key="attempt-1",
        status="outcome_unknown",
        provider_request_id="provider-42",
        error="Provider timeout after dispatch",
    )

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.attempts.save(attempt)
            await uow.commit()

    asyncio.run(_seed())
    res = runner.invoke(app, ["show", str(task.id).replace("-", "")[:8]])
    assert res.exit_code == 0
    assert "Outcome unknown" in res.stdout
    assert "provider-42" in res.stdout
    assert "Reconcile before retrying" in res.stdout
