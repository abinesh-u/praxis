"""praxis show — display full detail card for a specific task."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from praxis_cli.config import resolve_config
from praxis_cli.render import render_error, render_task_detail
from praxis_cli.wiring import get_uow, resolve_task_by_short_id


def show(
    task_id: Annotated[
        str,
        typer.Argument(help="Short ID or UUID of the task to inspect"),
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
    """Show comprehensive status, next actions, dependencies, and evidence for a task."""
    asyncio.run(_show(task_id, profile, timezone))


async def _show(task_id_str: str, profile: str | None, timezone: str | None) -> None:
    try:
        cfg = resolve_config(profile_override=profile, tz_override=timezone)
        uow = get_uow(cfg)

        async with uow:
            task = await resolve_task_by_short_id(uow, task_id_str, cfg.profile)

        render_task_detail(task, user_tz=cfg.timezone)
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
