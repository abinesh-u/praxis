"""Unit tests for ClarifyCommitmentUseCase."""

from datetime import datetime

import pytest
from praxis_core.entities.commitment import Commitment
from praxis_core.entities.common import Priority
from praxis_core.errors import EntityNotFoundError
from praxis_core.ports.task_extractor import ExtractedTaskData
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork
from praxis_core.use_cases.clarify_commitment import (
    ClarifyCommitmentCommand,
    ClarifyCommitmentUseCase,
)


class MockExtractor:
    def __init__(self, data: ExtractedTaskData) -> None:
        self.data = data

    async def extract(self, text: str, reference_time: datetime, user_timezone: str = "UTC"):
        return self.data


class TestClarifyCommitmentUseCase:
    """Verifies clarification submission, history preservation, and task creation."""

    @pytest.mark.anyio
    async def test_clarify_commitment_creates_task(self):
        uow = InMemoryUnitOfWork()
        commitment = Commitment(
            owner_id="user_1",
            raw_text="update the configuration",
            clarification_needed=True,
            clarification_prompt="Which environment configuration?",
        )

        async with uow:
            await uow.commitments.save(commitment)
            await uow.commit()

        clarified_data = ExtractedTaskData(
            title="Update staging environment configuration",
            description="Set staging database host",
            priority=Priority.IMPORTANT,
            next_action_description="Edit .env.staging file",
        )
        extractor = MockExtractor(clarified_data)
        use_case = ClarifyCommitmentUseCase(uow=uow, extractor=extractor)

        cmd = ClarifyCommitmentCommand(
            commitment_id=commitment.id,
            owner_id="user_1",
            clarification_response="I mean the staging environment",
        )
        result = await use_case.execute(cmd)

        assert result.clarification_needed is False
        assert result.task is not None
        assert result.task.title == "Update staging environment configuration"
        assert result.next_action is not None
        assert result.next_action.description == "Edit .env.staging file"

        # Check interpretation history was recorded
        saved_c = await uow.commitments.get_for_owner(commitment.id, "user_1")
        assert saved_c is not None
        assert len(saved_c.interpretation_history) >= 1

    @pytest.mark.anyio
    async def test_clarify_wrong_owner_raises_not_found(self):
        uow = InMemoryUnitOfWork()
        commitment = Commitment(owner_id="user_1", raw_text="vague")
        async with uow:
            await uow.commitments.save(commitment)
            await uow.commit()

        use_case = ClarifyCommitmentUseCase(
            uow=uow,
            extractor=MockExtractor(ExtractedTaskData(title="T")),
        )
        cmd = ClarifyCommitmentCommand(
            commitment_id=commitment.id,
            owner_id="wrong_user",
            clarification_response="info",
        )
        with pytest.raises(EntityNotFoundError):
            await use_case.execute(cmd)
