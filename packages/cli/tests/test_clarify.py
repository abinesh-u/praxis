"""Integration tests for praxis clarify."""

import asyncio
from pathlib import Path
from uuid import uuid4

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from praxis_core.entities.commitment import Commitment
from typer.testing import CliRunner

runner = CliRunner()


def test_clarify_commitment_flow(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    cid = uuid4()
    short_cid = str(cid).replace("-", "")[:8]

    # Pre-seed ambiguous commitment
    uow = JsonFileUnitOfWork(store_file)

    async def _seed():
        async with uow:
            c = Commitment(
                id=cid,
                owner_id="custom",
                raw_text="fix it",
                clarification_needed=True,
                clarification_prompt="What needs to be fixed?",
            )
            await uow.commitments.save(c)
            await uow.commit()

    asyncio.run(_seed())

    # Clarify
    res = runner.invoke(app, ["clarify", short_cid, "fix the auth token expiry check in jwt.py"])
    assert res.exit_code == 0
    assert "Commitment captured" in res.stdout

    # Verify task was created
    async def _check():
        async with uow:
            tasks = await uow.tasks.list_by_owner("custom")
            assert len(tasks) == 1
            assert "fix the auth token" in tasks[0].title.lower()

    asyncio.run(_check())
