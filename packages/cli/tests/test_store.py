"""Tests for JsonFileUnitOfWork and JSON repositories."""

from pathlib import Path
from uuid import uuid4

import pytest
from praxis_cli.store import (
    CorruptStorageError,
    JsonFileUnitOfWork,
    StorageLockTimeoutError,
    TransactionError,
)
from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
from praxis_core.entities.commitment import Commitment
from praxis_core.entities.common import ActionRiskLevel, Priority
from praxis_core.entities.execution_attempt import ExecutionAttempt
from praxis_core.entities.task import Task
from praxis_core.errors import ConcurrencyConflictError
from praxis_core.ports.unit_of_work import UnitOfWork


def test_unit_of_work_protocol_conformance(tmp_path: Path):
    store_file = tmp_path / "store.json"
    uow: UnitOfWork = JsonFileUnitOfWork(store_file)
    assert hasattr(uow, "tasks")
    assert hasattr(uow, "commitments")
    assert hasattr(uow, "approvals")
    assert hasattr(uow, "attempts")
    assert hasattr(uow, "audit_sink")
    assert callable(uow.commit)
    assert callable(uow.rollback)
    assert callable(uow.__aenter__)
    assert callable(uow.__aexit__)


@pytest.mark.anyio
async def test_store_creation_and_persistence(tmp_path: Path):
    store_file = tmp_path / "profiles" / "test" / "store.json"
    uow = JsonFileUnitOfWork(store_file)

    task_id = uuid4()
    async with uow:
        task = Task(
            id=task_id,
            owner_id="test_owner",
            title="Durable local task",
            priority=Priority.IMPORTANT,
        )
        uow.track_task(task)
        await uow.tasks.save(task)
        await uow.commit()

    assert (store_file.parent / "praxis.db").exists()

    # Reopen in new unit of work
    uow2 = JsonFileUnitOfWork(store_file)
    async with uow2:
        loaded = await uow2.tasks.get_for_owner(task_id, "test_owner")
        assert loaded is not None
        assert loaded.title == "Durable local task"
        assert loaded.priority == Priority.IMPORTANT

        # Verify audit event was flushed
        events = await uow2.audit_sink.list_for_aggregate(task_id)
        assert len(events) >= 1
        assert events[0].event_type == "task.created"


@pytest.mark.anyio
async def test_legacy_json_migration_to_sqlite(tmp_path: Path):
    """Legacy store.json records are seamlessly migrated to SQLite and archived."""
    store_file = tmp_path / "legacy" / "store.json"
    store_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_payload = {
        "schema_version": 1,
        "tasks": {
            "77777777-7777-7777-7777-777777777777": {
                "id": "77777777-7777-7777-7777-777777777777",
                "owner_id": "legacy_owner",
                "title": "Migrated legacy task",
                "status": "planned",
                "version": 1,
                "created_at": "2026-10-25T00:00:00Z",
                "updated_at": "2026-10-25T00:00:00Z",
                "dependencies": [],
                "next_actions": [],
                "evidence_records": [],
            }
        },
        "commitments": {},
        "approvals": {},
        "attempts": {},
        "audit_events": [],
    }
    import json

    store_file.write_text(json.dumps(legacy_payload), encoding="utf-8")
    (store_file.parent / "store.lock").touch()

    uow = JsonFileUnitOfWork(store_file)
    async with uow:
        migrated_task = await uow.tasks.get_for_owner(
            uuid4().__class__("77777777-7777-7777-7777-777777777777"), "legacy_owner"
        )
        assert migrated_task is not None
        assert migrated_task.title == "Migrated legacy task"

    # Verify original file archived and lock removed
    assert not store_file.exists()
    assert (store_file.parent / "store.json.migrated").exists()
    assert not (store_file.parent / "store.lock").exists()
    assert (store_file.parent / "praxis.db").exists()


@pytest.mark.anyio
async def test_rollback_on_exception(tmp_path: Path):
    store_file = tmp_path / "store.json"
    uow = JsonFileUnitOfWork(store_file)

    task_id = uuid4()
    with pytest.raises(RuntimeError, match="Simulated crash"):
        async with uow:
            task = Task(id=task_id, owner_id="test_owner", title="Uncommitted task")
            await uow.tasks.save(task)
            raise RuntimeError("Simulated crash")

    # In a new session, task must not exist
    uow2 = JsonFileUnitOfWork(store_file)
    async with uow2:
        loaded = await uow2.tasks.get_for_owner(task_id, "test_owner")
        assert loaded is None


@pytest.mark.anyio
async def test_corrupt_store_detection(tmp_path: Path):
    store_file = tmp_path / "store.json"
    store_file.write_text("{invalid json content!!!", encoding="utf-8")

    uow = JsonFileUnitOfWork(store_file)
    with pytest.raises(CorruptStorageError):
        async with uow:
            pass


@pytest.mark.anyio
async def test_optimistic_concurrency_conflict(tmp_path: Path):
    store_file = tmp_path / "store.json"
    uow = JsonFileUnitOfWork(store_file)

    task_id = uuid4()
    async with uow:
        task = Task(id=task_id, owner_id="test_owner", title="Concurrent task")
        await uow.tasks.save(task)
        await uow.commit()

    async with uow:
        loaded = await uow.tasks.get_for_owner(task_id, "test_owner")
        assert loaded is not None
        # Attempt save with wrong expected version
        with pytest.raises(ConcurrencyConflictError):
            await uow.tasks.save(loaded, expected_version=99)


@pytest.mark.anyio
async def test_lock_timeout_handling(tmp_path: Path):
    store_file = tmp_path / "store.json"
    uow1 = JsonFileUnitOfWork(store_file, lock_timeout_seconds=0.2)
    uow2 = JsonFileUnitOfWork(store_file, lock_timeout_seconds=0.2)

    async with uow1:
        # uow1 holds the sidecar lock; uow2 must raise StorageLockTimeoutError
        with pytest.raises(StorageLockTimeoutError, match="locked by another process"):
            async with uow2:
                pass


@pytest.mark.anyio
async def test_commit_outside_transaction_fails(tmp_path: Path):
    store_file = tmp_path / "store.json"
    uow = JsonFileUnitOfWork(store_file)
    with pytest.raises(TransactionError, match="outside an active transaction"):
        await uow.commit()


@pytest.mark.anyio
async def test_all_repositories_crud(tmp_path: Path):
    store_file = tmp_path / "store.json"
    uow = JsonFileUnitOfWork(store_file)

    tid = uuid4()
    cid = uuid4()

    async with uow:
        # Commitment
        commitment = Commitment(
            id=cid,
            owner_id="u1",
            raw_text="Call Alice",
            idempotency_key="key-alice",
        )
        await uow.commitments.save(commitment)

        # Task
        task = Task(id=tid, owner_id="u1", title="Call Alice", commitment_id=cid)
        await uow.tasks.save(task)

        # Approval
        action_spec = ActionSpecification(tool_name="test_tool", task_id=tid)
        approval, _ = ApprovalRequest.create(
            owner_id="u1",
            task_id=tid,
            action=action_spec,
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            justification="Requires approval",
        )
        await uow.approvals.save(approval)

        # Attempt
        attempt = ExecutionAttempt(
            owner_id="u1",
            task_id=tid,
            action_id=uuid4(),
            idempotency_key="attempt-1",
            status="running",
        )
        await uow.attempts.save(attempt)

        await uow.commit()

    # Re-read
    uow2 = JsonFileUnitOfWork(store_file)
    async with uow2:
        c = await uow2.commitments.find_by_idempotency_key("key-alice", "u1")
        assert c is not None
        assert c.id == cid

        pending_approvals = await uow2.approvals.list_pending("u1")
        assert len(pending_approvals) == 1

        att = await uow2.attempts.find_by_idempotency_key("attempt-1", "u1")
        assert att is not None
        assert att.status == "running"
