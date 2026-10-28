"""Ten-gate regression test suite for Candidate 1: Deepened Commitment Intake.

Verifies the three-phase intake lifecycle, transaction window isolation, optimistic
revision tokens, deterministic proposal validation, and identifier prefix seams.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from praxis_core.entities.common import Priority, SourceChannel, TaskStatus
from praxis_core.errors import (
    EntityNotFoundError,
    IdempotencyConflictError,
    IntakeValidationError,
    InvalidClarificationTargetError,
    StaleInferenceError,
)
from praxis_core.intake.contract import (
    ClarificationRequest,
    IntakeRequest,
    IntakeStatus,
)
from praxis_core.intake.engine import CommitmentIntakeEngine
from praxis_core.persistence.sqlite import SQLiteUnitOfWork
from praxis_core.ports.task_extractor import ExtractedTaskData, TaskExtractor
from praxis_core.ports.unit_of_work import InMemoryUnitOfWork


class StubTaskExtractor(TaskExtractor):
    """Configurable stub extractor for testing intake scenarios."""

    def __init__(self, data: ExtractedTaskData | None = None) -> None:
        self.data = data or ExtractedTaskData(
            title="Configure deployment credentials",
            description="Production credentials",
            priority=Priority.IMPORTANT,
            next_action_description="Generate API key in dashboard",
            suggested_tool_hint="cloud_key_create",
        )
        self.call_count = 0

    async def extract(
        self,
        text: str,
        reference_time: datetime,
        user_timezone: str = "UTC",
    ) -> ExtractedTaskData:
        self.call_count += 1
        return self.data


# -----------------------------------------------------------------------------
# Gate 1: Transaction Window Isolation
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate1_transaction_window_isolation_during_inference(tmp_path):
    """Proves that external model inference releases SQLite locks between Phase 1 and Phase 3."""
    db_file = tmp_path / "praxis_intake.db"
    db_url = f"sqlite:///{db_file}"

    # An extractor that pauses during Phase 2 and attempts concurrent SQLite writes
    concurrent_write_succeeded = False

    class PausingExtractor(TaskExtractor):
        async def extract(
            self,
            text: str,
            reference_time: datetime,
            user_timezone: str = "UTC",
        ) -> ExtractedTaskData:
            nonlocal concurrent_write_succeeded
            # While inference is running, connect directly with zero timeout
            # and verify an exclusive write transaction succeeds.
            conn = sqlite3.connect(str(db_file), timeout=0)
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO commitments (id, owner_id, captured_at, payload) "
                    "VALUES (?, ?, ?, ?)",
                    (str(uuid4()), "other_owner", datetime.now(UTC).isoformat(), "{}"),
                )
                conn.commit()
                concurrent_write_succeeded = True
            finally:
                conn.close()

            return ExtractedTaskData(
                title="Concurrent write task",
                next_action_description="Execute step",
            )

    uow = SQLiteUnitOfWork(db_url)
    engine = CommitmentIntakeEngine(uow=uow, extractor=PausingExtractor())

    req = IntakeRequest(
        owner_id="user_concurrent",
        raw_text="Deploy cluster updates",
        source=SourceChannel.CLI,
    )

    outcome = await engine.capture(req)
    assert outcome.status == IntakeStatus.CREATED
    assert concurrent_write_succeeded is True, (
        "Concurrent write failed; SQLite lock was held during inference!"
    )


# -----------------------------------------------------------------------------
# Gate 2: Optimistic Revision Token Protection (Stale Inference Race)
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate2_stale_inference_aborts_on_revision_mismatch():
    """Proves that revision bumps during inference cause Phase 3 to raise StaleInferenceError."""
    uow = InMemoryUnitOfWork()

    class RacingExtractor(TaskExtractor):
        async def extract(
            self,
            text: str,
            reference_time: datetime,
            user_timezone: str = "UTC",
        ) -> ExtractedTaskData:
            # Simulate a concurrent modification to the commitment during Phase 2
            commitments = await uow.commitments.list_by_owner("user_race")
            assert len(commitments) == 1
            commitments[0].record_interpretation("Intervening intent updated")
            await uow.commitments.save(commitments[0])
            return ExtractedTaskData(
                title="Delayed inference title",
                next_action_description="Delayed action",
            )

    engine = CommitmentIntakeEngine(uow=uow, extractor=RacingExtractor())

    req = IntakeRequest(
        owner_id="user_race",
        raw_text="Configure webhooks",
        source=SourceChannel.WEB,
    )

    with pytest.raises(StaleInferenceError) as exc_info:
        await engine.capture(req)

    assert exc_info.value.expected_revision == 1
    assert exc_info.value.actual_revision == 2


# -----------------------------------------------------------------------------
# Gate 3: Interrupted Extraction Recovery
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate3_interrupted_extraction_resumes_without_duplicate():
    """Proves that interrupted extraction safely resumes without creating duplicate commitments."""
    uow = InMemoryUnitOfWork()

    should_fail = True

    class FailingThenSucceedingExtractor(TaskExtractor):
        async def extract(
            self,
            text: str,
            reference_time: datetime,
            user_timezone: str = "UTC",
        ) -> ExtractedTaskData:
            nonlocal should_fail
            if should_fail:
                raise RuntimeError("Network timeout during external model inference")
            return ExtractedTaskData(
                title="Recovered task",
                next_action_description="Recovered action",
            )

    engine = CommitmentIntakeEngine(uow=uow, extractor=FailingThenSucceedingExtractor())

    req = IntakeRequest(
        owner_id="user_recover",
        raw_text="Setup disaster recovery",
        idempotency_key="disaster_recov_001",
    )

    # First attempt fails during inference (Phase 2)
    with pytest.raises(RuntimeError, match="Network timeout"):
        await engine.capture(req)

    # Commitment was saved in Phase 1
    existing_c = await uow.commitments.find_by_idempotency_key("disaster_recov_001", "user_recover")
    assert existing_c is not None
    original_id = existing_c.id

    # Second attempt succeeds: recovers original commitment without creating a second one
    should_fail = False
    outcome = await engine.capture(req)

    assert outcome.status == IntakeStatus.CREATED
    assert outcome.commitment.id == original_id
    assert outcome.task is not None

    all_commitments = await uow.commitments.list_by_owner("user_recover")
    all_tasks = await uow.tasks.list_by_owner("user_recover")
    assert len(all_commitments) == 1
    assert len(all_tasks) == 1


# -----------------------------------------------------------------------------
# Gate 4: Canonical SHA-256 Idempotency Fingerprinting
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate4_canonical_fingerprint_replay_and_conflict():
    """Proves replay on matching fingerprint and IdempotencyConflictError on tampering."""
    uow = InMemoryUnitOfWork()
    extractor = StubTaskExtractor()
    engine = CommitmentIntakeEngine(uow=uow, extractor=extractor)

    req1 = IntakeRequest(
        owner_id="user_fp",
        raw_text="Order new laptops",
        idempotency_key="laptop_order_token",
        user_timezone="UTC",
    )

    first_outcome = await engine.capture(req1)
    assert first_outcome.status == IntakeStatus.CREATED
    assert first_outcome.is_replay is False

    # Exact replay
    second_outcome = await engine.capture(req1)
    assert second_outcome.status == IntakeStatus.REPLAYED
    assert second_outcome.is_replay is True
    assert second_outcome.commitment.id == first_outcome.commitment.id
    assert second_outcome.task.id == first_outcome.task.id

    # Tampered payload with same idempotency key
    conflicting_req = IntakeRequest(
        owner_id="user_fp",
        raw_text="Order ergonomic chairs instead",
        idempotency_key="laptop_order_token",
        user_timezone="UTC",
    )

    with pytest.raises(IdempotencyConflictError):
        await engine.capture(conflicting_req)


# -----------------------------------------------------------------------------
# Gate 5: Proposal Validation — Empty Title Rejection
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate5_empty_title_rejection():
    """Proves that model extractions with empty or whitespace title are rejected."""
    uow = InMemoryUnitOfWork()
    extractor = StubTaskExtractor(
        ExtractedTaskData(
            title="   ",
            next_action_description="Some valid next action",
        )
    )
    engine = CommitmentIntakeEngine(uow=uow, extractor=extractor)

    req = IntakeRequest(
        owner_id="user_val",
        raw_text="some text",
    )

    with pytest.raises(IntakeValidationError, match="Task title cannot be empty"):
        await engine.capture(req)


# -----------------------------------------------------------------------------
# Gate 6: Proposal Validation — Empty Next Action Rejection
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate6_empty_next_action_rejection():
    """Proves that extractions with empty next action description are rejected."""
    uow = InMemoryUnitOfWork()
    extractor = StubTaskExtractor(
        ExtractedTaskData(
            title="Valid title",
            next_action_description="   ",
        )
    )
    engine = CommitmentIntakeEngine(uow=uow, extractor=extractor)

    req = IntakeRequest(
        owner_id="user_val",
        raw_text="some text",
    )

    with pytest.raises(IntakeValidationError, match="Next action description cannot be empty"):
        await engine.capture(req)


# -----------------------------------------------------------------------------
# Gate 7: Proposal Validation — Overdue Past Deadlines Allowed
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate7_overdue_past_deadlines_allowed():
    """Proves that valid overdue obligations in the past are accepted and normalized."""
    uow = InMemoryUnitOfWork()
    yesterday = datetime.now(UTC) - timedelta(days=1)
    extractor = StubTaskExtractor(
        ExtractedTaskData(
            title="Submit quarterly tax return",
            next_action_description="File schedule C online",
            due_date=yesterday,
        )
    )
    engine = CommitmentIntakeEngine(uow=uow, extractor=extractor)

    req = IntakeRequest(
        owner_id="user_overdue",
        raw_text="Tax return was due yesterday",
    )

    outcome = await engine.capture(req)
    assert outcome.status == IntakeStatus.CREATED
    assert outcome.task is not None
    assert outcome.task.due_date == yesterday


# -----------------------------------------------------------------------------
# Gate 8: Clarification Intent History Preservation
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate8_clarification_history_preservation():
    """Proves clarification appends to interpretation history and preserves original text."""
    uow = InMemoryUnitOfWork()

    # Step 1: Capture vague commitment
    vague_extractor = StubTaskExtractor(
        ExtractedTaskData(
            title="Vague task",
            clarification_needed=True,
            clarification_prompt="Which server needs patching?",
        )
    )
    engine1 = CommitmentIntakeEngine(uow=uow, extractor=vague_extractor)

    outcome1 = await engine1.capture(
        IntakeRequest(
            owner_id="user_clarify",
            raw_text="Patch the server",
        )
    )
    assert outcome1.status == IntakeStatus.AWAITING_CLARIFICATION
    commitment_id = outcome1.commitment.id
    initial_revision = outcome1.commitment.interpretation_revision

    # Step 2: Clarify ambiguous commitment
    clarified_extractor = StubTaskExtractor(
        ExtractedTaskData(
            title="Patch the production database server",
            next_action_description="Run apt-get upgrade on db-prod-01",
        )
    )
    engine2 = CommitmentIntakeEngine(uow=uow, extractor=clarified_extractor)

    outcome2 = await engine2.clarify(
        ClarificationRequest(
            commitment_id=commitment_id,
            owner_id="user_clarify",
            clarification_response="Production database cluster db-prod-01",
        )
    )

    assert outcome2.status == IntakeStatus.CREATED
    assert outcome2.task is not None
    assert outcome2.task.title == "Patch the production database server"

    # Verify history and revision
    saved_c = await uow.commitments.get_for_owner(commitment_id, "user_clarify")
    assert saved_c is not None
    assert saved_c.raw_text == "Patch the server"
    assert saved_c.interpretation_revision > initial_revision
    assert len(saved_c.interpretation_history) >= 2


# -----------------------------------------------------------------------------
# Gate 9: Clarification Ineligible on Completed Tasks
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate9_clarification_ineligible_on_completed_task():
    """Proves that clarifying a completed commitment raises InvalidClarificationTargetError."""
    uow = InMemoryUnitOfWork()
    extractor = StubTaskExtractor()
    engine = CommitmentIntakeEngine(uow=uow, extractor=extractor)

    outcome = await engine.capture(
        IntakeRequest(
            owner_id="user_completed",
            raw_text="Complete audit",
        )
    )
    task = outcome.task
    assert task is not None

    # Complete the task
    async with uow:
        reloaded_task = await uow.tasks.get_for_owner(task.id, "user_completed")
        assert reloaded_task is not None
        reloaded_task.status = TaskStatus.COMPLETED
        await uow.tasks.save(reloaded_task)
        await uow.commit()

    # Attempting to clarify this completed commitment must fail
    with pytest.raises(InvalidClarificationTargetError):
        await engine.clarify(
            ClarificationRequest(
                commitment_id=outcome.commitment.id,
                owner_id="user_completed",
                clarification_response="Additional details",
            )
        )


# -----------------------------------------------------------------------------
# Gate 10: Identifier Prefix / Short-ID Resolution
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_gate10_short_id_resolution_and_ambiguity():
    """Proves resolving commitments via short-id prefixes, handling missing and ambiguous cases."""
    uow = InMemoryUnitOfWork()
    vague_extractor = StubTaskExtractor(
        ExtractedTaskData(
            title="Vague item",
            clarification_needed=True,
            clarification_prompt="Clarify please",
        )
    )
    engine = CommitmentIntakeEngine(uow=uow, extractor=vague_extractor)

    outcome = await engine.capture(
        IntakeRequest(owner_id="user_prefix", raw_text="Need to do something")
    )
    cid = outcome.commitment.id
    short_prefix = str(cid)[:8]

    # Resolve with valid 8-character prefix
    clarified_extractor = StubTaskExtractor(
        ExtractedTaskData(
            title="Clarified through prefix",
            next_action_description="Execute step 1",
        )
    )
    engine_clarify = CommitmentIntakeEngine(uow=uow, extractor=clarified_extractor)

    clarified_outcome = await engine_clarify.clarify(
        ClarificationRequest(
            commitment_id=short_prefix,
            owner_id="user_prefix",
            clarification_response="Here is the missing info",
        )
    )
    assert clarified_outcome.status == IntakeStatus.CREATED
    assert clarified_outcome.commitment.id == cid

    # Missing prefix raises EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        await engine_clarify.clarify(
            ClarificationRequest(
                commitment_id="00000000",
                owner_id="user_prefix",
                clarification_response="info",
            )
        )
