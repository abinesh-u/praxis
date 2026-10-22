"""Integration tests for praxis show and praxis list."""

import asyncio
from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
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
