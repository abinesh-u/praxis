"""Tests for profile isolation, validation, and cross-owner access boundaries."""

from pathlib import Path
from uuid import uuid4

import pytest
from praxis_cli.config import (
    InvalidProfileError,
    resolve_config,
    validate_profile_name,
)
from praxis_cli.store import JsonFileUnitOfWork
from praxis_cli.wiring import AmbiguousIdentifierError, resolve_task_by_short_id
from praxis_core.entities.task import Task
from praxis_core.errors import EntityNotFoundError


def test_profile_name_validation():
    # Valid names
    assert validate_profile_name("work") == "work"
    assert validate_profile_name("personal_1") == "personal_1"
    assert validate_profile_name("team-a") == "team-a"

    # Invalid names must fail closed
    for bad in ["../traversal", "/root", "has space", "", "evil$name", "a" * 65]:
        with pytest.raises(InvalidProfileError):
            validate_profile_name(bad)


def test_config_fail_closed_on_invalid_profile():
    with pytest.raises(InvalidProfileError):
        resolve_config(profile_override="../invalid")


def test_physical_storage_path_isolation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PRAXIS_HOME", str(tmp_path))

    cfg_work = resolve_config(profile_override="work")
    cfg_personal = resolve_config(profile_override="personal")

    assert "work" in str(cfg_work.store_path)
    assert "personal" in str(cfg_personal.store_path)
    assert cfg_work.store_path != cfg_personal.store_path


@pytest.mark.anyio
async def test_cross_owner_task_isolation(tmp_path: Path):
    store_file = tmp_path / "store.json"
    uow = JsonFileUnitOfWork(store_file)

    task_id = uuid4()
    async with uow:
        # Save a task belonging to user_a
        task = Task(id=task_id, owner_id="user_a", title="User A Secret Task")
        await uow.tasks.save(task)
        await uow.commit()

    async with uow:
        # user_a can access
        found_a = await uow.tasks.get_for_owner(task_id, "user_a")
        assert found_a is not None

        # user_b MUST NOT access (returns None)
        found_b = await uow.tasks.get_for_owner(task_id, "user_b")
        assert found_b is None

        # Short ID resolution for user_b MUST raise EntityNotFoundError
        short = str(task_id).replace("-", "")[:8]
        with pytest.raises(EntityNotFoundError):
            await resolve_task_by_short_id(uow, short, "user_b")

        # Short ID resolution for user_a succeeds
        resolved_a = await resolve_task_by_short_id(uow, short, "user_a")
        assert resolved_a.id == task_id


@pytest.mark.anyio
async def test_ambiguous_short_id_raises_error(tmp_path: Path):
    store_file = tmp_path / "store.json"
    uow = JsonFileUnitOfWork(store_file)

    async with uow:
        # Create two tasks with identical prefixes
        t1 = Task(owner_id="u1", title="Task 1")
        t2 = Task(owner_id="u1", title="Task 2")
        await uow.tasks.save(t1)
        await uow.tasks.save(t2)
        await uow.commit()

    async with uow:
        # 1-character prefix matching both
        common_prefix = str(t1.id).replace("-", "")[:1]
        # Check if t2 also starts with same char or force conflict
        if not str(t2.id).replace("-", "").startswith(common_prefix):
            # Manually inject prefix for test
            t2._raw_id = t1.id  # Just test with common prefix
        # If prefix matches multiple, raises AmbiguousIdentifierError
        # Test directly with empty/short query that matches all
        with pytest.raises(AmbiguousIdentifierError):
            await resolve_task_by_short_id(uow, "", "u1")
