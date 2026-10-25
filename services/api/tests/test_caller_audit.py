"""Tests validating that audited list_by_owner callers operate reliably at scale."""

from datetime import datetime
from uuid import UUID, uuid4

import httpx
import pytest
from praxis_api.main import create_app
from praxis_api.persistence import SQLiteUnitOfWork
from praxis_cli.wiring import AmbiguousIdentifierError, resolve_task_by_short_id
from praxis_core.entities.common import Priority, TaskStatus
from praxis_core.entities.task import Task
from praxis_core.ports.task_extractor import ExtractedTaskData
from praxis_core.use_cases import CaptureCommitmentCommand, CaptureCommitmentUseCase


class MockExtractor:
    async def extract(self, text: str, reference_time: datetime, user_timezone: str = "UTC"):
        return ExtractedTaskData(
            title="Extracted Task",
            description=text,
            priority=Priority.IMPORTANT,
            next_action_description="Next action",
        )


def _url(tmp_path, name="audit.db") -> str:
    return f"sqlite:///{tmp_path / name}"


@pytest.mark.anyio
async def test_capture_commitment_replay_with_150_tasks(tmp_path):
    """An idempotent capture replay with 150 tasks finds the task via find_by_commitment_id."""
    url = _url(tmp_path, "replay150.db")
    uow = SQLiteUnitOfWork(url)
    use_case = CaptureCommitmentUseCase(uow=uow, extractor=MockExtractor())

    # First capture
    cmd = CaptureCommitmentCommand(
        owner_id="heavy_user",
        raw_text="Commitment to replay",
        idempotency_key="unique-replay-key",
    )
    result_1 = await use_case.execute(cmd)
    original_task_id = result_1.task.id

    # Seed 150 additional tasks for the same owner
    async with uow:
        for i in range(150):
            await uow.tasks.save(Task(owner_id="heavy_user", title=f"Distractor {i}"))
        await uow.commit()

    # Replay capture with the exact same idempotency key
    result_2 = await use_case.execute(cmd)
    assert result_2.task is not None
    assert result_2.task.id == original_task_id


@pytest.mark.anyio
async def test_status_counts_with_150_tasks(tmp_path):
    """count_by_status returns exact counts grouped by status across 150 tasks."""
    url = _url(tmp_path, "counts150.db")
    uow = SQLiteUnitOfWork(url)

    async with uow:
        # Seed tasks across multiple statuses
        for _ in range(50):
            await uow.tasks.save(
                Task(owner_id="count_user", title="Planned", status=TaskStatus.PLANNED)
            )
        for _ in range(60):
            await uow.tasks.save(
                Task(owner_id="count_user", title="In Progress", status=TaskStatus.IN_PROGRESS)
            )
        for _ in range(40):
            await uow.tasks.save(
                Task(owner_id="count_user", title="Completed", status=TaskStatus.COMPLETED)
            )
        await uow.commit()

    async with uow:
        counts = await uow.tasks.count_by_status("count_user")
        assert counts[TaskStatus.PLANNED] == 50
        assert counts[TaskStatus.IN_PROGRESS] == 60
        assert counts[TaskStatus.COMPLETED] == 40
        assert counts[TaskStatus.FAILED] == 0


@pytest.mark.anyio
async def test_short_id_prefix_resolution_with_150_tasks(tmp_path):
    """resolve_task_by_short_id resolves a task using find_by_id_prefix even among 150 tasks."""
    url = _url(tmp_path, "prefix150.db")
    uow = SQLiteUnitOfWork(url)

    target_task = Task(
        id=UUID("abcdef12-0000-0000-0000-000000000001"), owner_id="prefix_user", title="Target"
    )
    async with uow:
        await uow.tasks.save(target_task)
        # Seed 150 distractors
        for i in range(150):
            await uow.tasks.save(Task(id=uuid4(), owner_id="prefix_user", title=f"Distractor {i}"))
        await uow.commit()

    async with uow:
        resolved = await resolve_task_by_short_id(uow, "abcdef12", "prefix_user")
        assert resolved.id == target_task.id


@pytest.mark.anyio
async def test_ambiguous_prefix_resolution_raises_error(tmp_path):
    """When multiple tasks share an ID prefix, rejection occurs with AmbiguousIdentifierError."""
    url = _url(tmp_path, "ambig.db")
    uow = SQLiteUnitOfWork(url)

    task_1 = Task(
        id=UUID("aaaaaaaa-1111-0000-0000-000000000001"), owner_id="prefix_user", title="Task 1"
    )
    task_2 = Task(
        id=UUID("aaaaaaaa-2222-0000-0000-000000000002"), owner_id="prefix_user", title="Task 2"
    )

    async with uow:
        await uow.tasks.save(task_1)
        await uow.tasks.save(task_2)
        await uow.commit()

    async with uow:
        with pytest.raises(AmbiguousIdentifierError, match="matches 2 tasks"):
            await resolve_task_by_short_id(uow, "aaaaaaaa", "prefix_user")


@pytest.mark.anyio
async def test_api_route_tasks_pagination(tmp_path):
    """GET /tasks honors limit, offset, and computes has_more accurately."""
    url = _url(tmp_path, "api_paged.db")
    app = create_app(url)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed 5 tasks via API
        for i in range(5):
            res = await client.post(
                "/tasks",
                json={
                    "owner_id": "api_pager",
                    "raw_text": f"Task number {i}",
                    "source": "api",
                },
            )
            assert res.status_code == 201

        # Page 1: limit 2 -> has_more True
        r1 = await client.get("/tasks", params={"owner_id": "api_pager", "limit": 2, "offset": 0})
        assert r1.status_code == 200
        d1 = r1.json()
        assert len(d1["tasks"]) == 2
        assert d1["limit"] == 2
        assert d1["offset"] == 0
        assert d1["has_more"] is True

        # Page 2: limit 2, offset 2 -> has_more True
        r2 = await client.get("/tasks", params={"owner_id": "api_pager", "limit": 2, "offset": 2})
        assert r2.status_code == 200
        d2 = r2.json()
        assert len(d2["tasks"]) == 2
        assert d2["has_more"] is True

        # Page 3: limit 2, offset 4 -> has_more False (only 1 task remaining)
        r3 = await client.get("/tasks", params={"owner_id": "api_pager", "limit": 2, "offset": 4})
        assert r3.status_code == 200
        d3 = r3.json()
        assert len(d3["tasks"]) == 1
        assert d3["has_more"] is False
