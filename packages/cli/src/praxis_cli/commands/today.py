"""praxis today — display daily prioritized agenda with spotlight next action."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated

import typer

from praxis_cli.api_client import PraxisApiClient
from praxis_cli.config import resolve_config
from praxis_cli.render import (
    console,
    latest_attempt,
    render_agenda_table,
    render_api_agenda,
    render_error,
    render_spotlight,
)
from praxis_cli.wiring import get_uow, make_agenda_use_case


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
    api: Annotated[
        bool,
        typer.Option("--api", help="Use the shared API instead of local JSON storage"),
    ] = False,
) -> None:
    """Show today's prioritized agenda: immediate next action spotlight and ready queue."""
    asyncio.run(_today(date, profile, timezone, api))


async def _today(
    date_str: str | None,
    profile: str | None,
    timezone: str | None,
    api: bool = False,
) -> None:
    try:
        cfg = resolve_config(profile_override=profile, tz_override=timezone)
        target_date = datetime.fromisoformat(date_str) if date_str else None

        if api:
            with PraxisApiClient(cfg.api_url) as client:
                agenda = client.today(owner_id=cfg.profile, at=target_date)
            render_api_agenda(agenda)
            return

        use_case = make_agenda_use_case(cfg)
        agenda = await use_case.execute(owner_id=cfg.profile, date=target_date)

        # Attempts are durable execution state, so include them without changing
        # the domain agenda contract. An uncertain attempt is never presented as
        # ready to retry.
        attempts_by_task = {}
        async with get_uow(cfg) as attempt_uow:
            for item in [*agenda.actionable, *agenda.waiting]:
                attempts_by_task[item.task.id] = await attempt_uow.attempts.list_for_task(
                    item.task.id, cfg.profile
                )
        unknown_items = []
        actionable = []
        for item in agenda.actionable:
            attempt = latest_attempt(attempts_by_task.get(item.task.id, []))
            if attempt and attempt.status == "outcome_unknown":
                item.waiting_reason = "Outcome unknown — reconcile before retrying"
                item.is_blocked = True
                unknown_items.append(item)
            else:
                actionable.append(item)
        waiting = [*agenda.waiting, *unknown_items]

        # 1. Spotlight on the single #1 immediate action
        if actionable:
            render_spotlight(actionable[0], user_tz=cfg.timezone)

        # 2. Queue of remaining ready and waiting items
        remaining_actionable = actionable[1:] if len(actionable) > 1 else []
        if remaining_actionable or waiting:
            ready_count = len(actionable)
            wait_count = len(waiting)
            console.print(
                f"\n[bold white]📋 TODAY'S QUEUE[/bold white] "
                f"([green3]{ready_count} ready[/green3], [grey62]{wait_count} waiting[/grey62])\n"
            )
            render_agenda_table(
                remaining_actionable,
                waiting,
                user_tz=cfg.timezone,
                attempts_by_task=attempts_by_task,
            )
        elif not actionable:
            console.print("  ✨ No active tasks on your agenda.\n", style="grey62")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
