"""Integration tests for praxis complete and praxis defer."""

import asyncio
from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.common import TaskStatus
from praxis_core.entities.task import Task
from typer.testing import CliRunner

runner = CliRunner()


def test_complete_task_with_evidence(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Manual Filing", status=TaskStatus.PLANNED)

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

    asyncio.run(_seed())

    short_id = str(task.id).replace("-", "")[:8]
    res = runner.invoke(
        app, ["complete", short_id, "--note", "Signed and filed document in cabinet"]
    )
    assert res.exit_code == 0
    assert "marked COMPLETED" in res.stdout
    assert "Signed and filed document" in res.stdout

    # Verify task state in store
    async def _check():
        async with uow:
            t = await uow.tasks.get_for_owner(task.id, "custom")
            assert t.status == TaskStatus.COMPLETED
            assert len(t.evidence_records) == 1

    asyncio.run(_check())


def test_defer_task_guilt_free(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    uow = JsonFileUnitOfWork(store_file)
    task = Task(owner_id="custom", title="Annual Tax Review", status=TaskStatus.PLANNED)

    async def _seed():
        async with uow:
            await uow.tasks.save(task)
            await uow.commit()

    asyncio.run(_seed())

    short_id = str(task.id).replace("-", "")[:8]
    res = runner.invoke(
        app, ["defer", short_id, "--until", "tomorrow", "--reason", "Waiting on 1099 form"]
    )
    assert res.exit_code == 0
    assert "deferred to" in res.stdout
    assert "no rush" in res.stdout

    # Verify deferral count incremented
    async def _check():
        async with uow:
            t = await uow.tasks.get_for_owner(task.id, "custom")
            assert t.status == TaskStatus.DEFERRED
            assert t.deferral_count == 1
            assert t.deferred_until is not None

    asyncio.run(_check())
