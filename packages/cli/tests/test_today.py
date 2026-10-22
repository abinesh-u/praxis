"""Integration tests for praxis today."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.common import Priority, TaskStatus
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
