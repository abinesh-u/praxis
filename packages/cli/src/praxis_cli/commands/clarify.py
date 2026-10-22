"""praxis clarify — clarify an ambiguous commitment command."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from praxis_core.use_cases import ClarifyCommitmentCommand

from praxis_cli.config import resolve_config
from praxis_cli.render import render_capture_result, render_error
from praxis_cli.wiring import (
    get_uow,
    make_clarify_use_case,
    resolve_commitment_by_short_id,
)


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
        uow = get_uow(cfg)

        async with uow:
            commitment = await resolve_commitment_by_short_id(uow, commitment_id, cfg.profile)

        use_case = make_clarify_use_case(cfg)
        cmd = ClarifyCommitmentCommand(
            commitment_id=commitment.id,
            owner_id=cfg.profile,
            clarification_response=response,
            user_timezone=cfg.timezone,
        )
        result = await use_case.execute(cmd)
        render_capture_result(result, user_tz=cfg.timezone)
        if result.clarification_needed:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
