"""Unit tests for CaptureCommitmentUseCase."""

from datetime import datetime

import pytest
from praxis_core.entities.common import Priority, SourceChannel, TaskStatus
from praxis_core.ports.task_extractor import ExtractedTaskData
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
from praxis_core.use_cases.capture_commitment import (
    CaptureCommitmentCommand,
    CaptureCommitmentUseCase,
)


class MockExtractor:
    """Mock extractor returning pre-configured data or simulated responses."""

    def __init__(self, data: ExtractedTaskData | None = None) -> None:
        self.data = data or ExtractedTaskData(
            title="Renew SSL certificates",
            description="Production certs expire in 3 days",
            priority=Priority.IMPORTANT,
            next_action_description="Check certbot expiration via shell",
            suggested_tool_hint="shell_run",
        )

    async def extract(self, text: str, reference_time: datetime, user_timezone: str = "UTC"):
        return self.data


class TestCaptureCommitmentUseCase:
    """Verifies commitment capture, task decomposition, and event dispatch."""

    @pytest.mark.anyio
    async def test_capture_commitment_happy_path(self):
        uow = InMemoryUnitOfWork()
        extractor = MockExtractor()
        use_case = CaptureCommitmentUseCase(uow=uow, extractor=extractor)

        cmd = CaptureCommitmentCommand(
            owner_id="user_123",
            raw_text="Renew SSL certificates before Friday",
            source=SourceChannel.CLI,
            user_timezone="UTC",
        )

        result = await use_case.execute(cmd)

        assert result.clarification_needed is False
        assert result.commitment.owner_id == "user_123"
        assert result.commitment.raw_text == "Renew SSL certificates before Friday"

        assert result.task is not None
        assert result.task.owner_id == "user_123"
        assert result.task.title == "Renew SSL certificates"
        assert result.task.status == TaskStatus.PLANNED
        assert result.task.priority == Priority.IMPORTANT

        assert result.next_action is not None
        assert result.next_action.description == "Check certbot expiration via shell"

        # Verify audit event emitted
        events = uow.audit_sink.get_events(aggregate_id=result.task.id)
        assert len(events) >= 1
        assert events[0].event_type == "task.created"

    @pytest.mark.anyio
    async def test_capture_vague_commitment_requests_clarification_without_task(self):
        uow = InMemoryUnitOfWork()
        vague_data = ExtractedTaskData(
            title="Vague task",
            clarification_needed=True,
            clarification_prompt="What specific files need updating?",
        )
        extractor = MockExtractor(data=vague_data)
        use_case = CaptureCommitmentUseCase(uow=uow, extractor=extractor)

        cmd = CaptureCommitmentCommand(
            owner_id="user_123",
            raw_text="fix the stuff",
        )

        result = await use_case.execute(cmd)

        assert result.clarification_needed is True
        assert result.clarification_prompt == "What specific files need updating?"
        assert result.task is None
        assert result.next_action is None

        # Commitment record is saved with prompt
        saved_c = await uow.commitments.get_for_owner(result.commitment.id, "user_123")
        assert saved_c is not None
        assert saved_c.clarification_needed is True

    @pytest.mark.anyio
    async def test_capture_commitment_idempotency_prevents_duplicate_tasks(self):
        uow = InMemoryUnitOfWork()
        extractor = MockExtractor()
        use_case = CaptureCommitmentUseCase(uow=uow, extractor=extractor)

        cmd = CaptureCommitmentCommand(
            owner_id="user_123",
            raw_text="Renew SSL certificates before Friday",
            idempotency_key="unique_capture_token_abc123",
        )

        first_result = await use_case.execute(cmd)
        second_result = await use_case.execute(cmd)

        # Same IDs returned
        assert first_result.commitment.id == second_result.commitment.id
        assert first_result.task.id == second_result.task.id

        # No duplicate commitments or tasks saved
        all_commitments = await uow.commitments.list_by_owner("user_123")
        all_tasks = await uow.tasks.list_by_owner("user_123")
        assert len(all_commitments) == 1
        assert len(all_tasks) == 1
