"""praxis today — display daily prioritized agenda with spotlight next action."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated

import typer

from praxis_cli.config import resolve_config
from praxis_cli.render import console, render_agenda_table, render_error, render_spotlight
from praxis_cli.wiring import make_agenda_use_case


def today(
    date: Annotated[
        str | None,
        typer.Option("--date", "-d", help="Target date in ISO format (YYYY-MM-DD)"),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
    timezone: Annotated[
        str | None,
        typer.Option("--tz", help="Timezone override"),
    ] = None,
) -> None:
    """Show today's prioritized agenda: immediate next action spotlight and ready queue."""
    asyncio.run(_today(date, profile, timezone))


async def _today(
    date_str: str | None,
    profile: str | None,
    timezone: str | None,
) -> None:
    try:
        cfg = resolve_config(profile_override=profile, tz_override=timezone)
        target_date = datetime.fromisoformat(date_str) if date_str else None

        use_case = make_agenda_use_case(cfg)
        agenda = await use_case.execute(owner_id=cfg.profile, date=target_date)

        # 1. Spotlight on the single #1 immediate action
        if agenda.actionable:
            render_spotlight(agenda.actionable[0], user_tz=cfg.timezone)

        # 2. Queue of remaining ready and waiting items
        remaining_actionable = agenda.actionable[1:] if len(agenda.actionable) > 1 else []
        if remaining_actionable or agenda.waiting:
            ready_count = len(agenda.actionable)
            wait_count = len(agenda.waiting)
            console.print(
                f"\n[bold white]📋 TODAY'S QUEUE[/bold white] "
                f"([green3]{ready_count} ready[/green3], [grey62]{wait_count} waiting[/grey62])\n"
            )
            render_agenda_table(remaining_actionable, agenda.waiting, user_tz=cfg.timezone)
        elif not agenda.actionable:
            console.print("  ✨ No active tasks on your agenda.\n", style="grey62")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
