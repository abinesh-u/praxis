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
            all_tasks = await uow.tasks.list_by_owner(cfg.profile)
            pending_approvals = await uow.approvals.list_pending(cfg.profile)

        terminal_states = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        active = [t for t in all_tasks if t.status not in terminal_states]
        in_prog = [t for t in all_tasks if t.status == TaskStatus.IN_PROGRESS]
        awaiting_appr = [t for t in all_tasks if t.status == TaskStatus.AWAITING_APPROVAL]
        failed = [t for t in all_tasks if t.status == TaskStatus.FAILED]

        console.print(f"[bold sky_blue1]Praxis Status — Profile: {cfg.profile}[/bold sky_blue1]\n")
        console.print(f"  Active Tasks:       [bold white]{len(active)}[/bold white]")
        console.print(f"  In Progress:        [sky_blue1]{len(in_prog)}[/sky_blue1]")
        console.print(
            f"  Awaiting Approval:  [yellow3]{len(awaiting_appr)}[/yellow3] "
            f"({len(pending_approvals)} request tokens)"
        )
        console.print(f"  Needs Attention:    [indian_red1]{len(failed)}[/indian_red1]")
        console.print(f"  Timezone:           [grey62]{cfg.timezone}[/grey62]\n")
        console.print("Run [bold white]praxis today[/bold white] to see your current action.")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
