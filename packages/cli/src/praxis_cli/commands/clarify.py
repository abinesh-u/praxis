"""praxis clarify — clarify an ambiguous commitment command."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from praxis_core.intake import ClarificationRequest, IntakeStatus
from praxis_core.use_cases import CaptureCommitmentResult

from praxis_cli.config import resolve_config
from praxis_cli.render import render_capture_result, render_error
from praxis_cli.wiring import make_commitment_intake_engine


def clarify(
    commitment_id: Annotated[
        str,
        typer.Argument(help="Short ID or UUID of the commitment needing clarification"),
    ],
    response: Annotated[
        str,
        typer.Argument(help="Clarification details to resolve the commitment"),
    ],
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
    timezone: Annotated[
        str | None,
        typer.Option("--tz", help="Timezone override"),
    ] = None,
) -> None:
    """Provide clarification for an ambiguous commitment to re-extract task objectives."""
    asyncio.run(_clarify(commitment_id, response, profile, timezone))


async def _clarify(
    commitment_id: str,
    response: str,
    profile: str | None,
    timezone: str | None,
) -> None:
    try:
        cfg = resolve_config(profile_override=profile, tz_override=timezone)
        engine = make_commitment_intake_engine(cfg)
        cmd = ClarificationRequest(
            commitment_id=commitment_id,
            owner_id=cfg.profile,
            clarification_response=response,
            user_timezone=cfg.timezone,
        )
        outcome = await engine.clarify(cmd)
        result = CaptureCommitmentResult(
            commitment=outcome.commitment,
            task=outcome.task,
            next_action=outcome.next_action,
            clarification_needed=(outcome.status == IntakeStatus.AWAITING_CLARIFICATION),
            clarification_prompt=outcome.clarification_prompt,
        )
        render_capture_result(result, user_tz=cfg.timezone)
        if result.clarification_needed:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
