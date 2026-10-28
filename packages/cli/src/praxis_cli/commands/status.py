"""praxis status — overview of current profile obligations and pending decisions."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from praxis_core.entities.common import TaskStatus

from praxis_cli.config import resolve_config
from praxis_cli.render import console, render_error
from praxis_cli.wiring import get_uow


def status(
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
) -> None:
    """Show quick summary of active obligations, approvals, and system state."""
    asyncio.run(_status(profile))


async def _status(profile: str | None) -> None:
    try:
        cfg = resolve_config(profile_override=profile)
        uow = get_uow(cfg)

        async with uow:
            counts = await uow.tasks.count_by_status(cfg.profile)
            pending_approvals = await uow.approvals.list_pending(cfg.profile)

        terminal_states = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        active_count = sum(cnt for status, cnt in counts.items() if status not in terminal_states)
        in_prog_count = counts.get(TaskStatus.IN_PROGRESS, 0)
        awaiting_appr_count = counts.get(TaskStatus.AWAITING_APPROVAL, 0)
        failed_count = counts.get(TaskStatus.FAILED, 0)

        console.print(f"[bold sky_blue1]Praxis Status — Profile: {cfg.profile}[/bold sky_blue1]\n")
        console.print(f"  Active Tasks:       [bold white]{active_count}[/bold white]")
        console.print(f"  In Progress:        [sky_blue1]{in_prog_count}[/sky_blue1]")
        console.print(
            f"  Awaiting Approval:  [yellow3]{awaiting_appr_count}[/yellow3] "
            f"({len(pending_approvals)} request tokens)"
        )
        console.print(f"  Needs Attention:    [indian_red1]{failed_count}[/indian_red1]")
        console.print(f"  Timezone:           [grey62]{cfg.timezone}[/grey62]\n")
        console.print("Run [bold white]praxis today[/bold white] to see your current action.")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
