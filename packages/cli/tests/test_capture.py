"""Integration tests for praxis capture."""

from pathlib import Path

from praxis_cli.main import app
from praxis_cli.store import JsonFileUnitOfWork
from typer.testing import CliRunner

runner = CliRunner()


def test_capture_commitment_offline_fallback(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    result = runner.invoke(app, ["capture", "Draft presentation slides for Friday demo"])
    assert result.exit_code == 0
    assert "Commitment captured" in result.stdout
    assert "Draft presentation slides" in result.stdout
    assert "Short ID:" in result.stdout


def test_capture_vague_input_triggers_clarification(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    result = runner.invoke(app, ["capture", "do it"])
    assert result.exit_code == 1
    assert "Clarification Needed" in result.stdout
    assert "praxis clarify" in result.stdout


def test_capture_idempotency_replay(tmp_path: Path, monkeypatch):
    store_file = tmp_path / "store.json"
    monkeypatch.setenv("PRAXIS_STORE_PATH", str(store_file))

    # First capture
    res1 = runner.invoke(app, ["capture", "Review pull request 101", "--key", "idem-pr-101"])
    assert res1.exit_code == 0

    # Repeat capture with same key
    res2 = runner.invoke(app, ["capture", "Review pull request 101", "--key", "idem-pr-101"])
    assert res2.exit_code == 0

    # Verify only 1 commitment and 1 task in store
    uow = JsonFileUnitOfWork(store_file)
    import asyncio

    async def _check():
        async with uow:
            tasks = await uow.tasks.list_by_owner("custom")
            assert len(tasks) == 1

    asyncio.run(_check())
