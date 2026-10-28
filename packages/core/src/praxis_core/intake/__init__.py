"""Intake module exposing the commitment intake engine, validator, and contracts.

This module provides high depth and locality for natural language commitment intake,
enabling CLI and HTTP adapters to interact with a uniform execution seam.
"""

from praxis_core.intake.contract import (
    ClarificationRequest,
    IntakeOutcome,
    IntakeRequest,
    IntakeStatus,
)
from praxis_core.intake.engine import CommitmentIntakeEngine
from praxis_core.intake.validator import IntakeProposalValidator, ValidatedProposal

__all__ = [
    "ClarificationRequest",
    "CommitmentIntakeEngine",
    "IntakeOutcome",
    "IntakeProposalValidator",
    "IntakeRequest",
    "IntakeStatus",
    "ValidatedProposal",
]
