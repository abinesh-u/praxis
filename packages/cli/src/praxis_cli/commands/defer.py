"""praxis defer — guilt-free task deferral and rescheduling."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

import typer
from praxis_core.use_cases import DeferTaskCommand

from praxis_cli.config import resolve_config
from praxis_cli.render import console, format_dt, render_error, short_id
from praxis_cli.wiring import get_uow, make_defer_use_case, resolve_task_by_short_id


def defer(
    task_id: Annotated[
        str,
        typer.Argument(help="Short ID or UUID of the task to defer"),
    ],
    until: Annotated[
        str,
        typer.Option("--until", "-u", help="New target date/time ('tomorrow', '+1d', '+2h', ISO)"),
    ],
    reason: Annotated[
        str | None,
        typer.Option("--reason", "-r", help="Optional context note for rescheduling"),
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
    """Postpone a task to a future time with zero guilt and no streak pressure."""
    asyncio.run(_defer(task_id, until, reason, profile, timezone))


async def _defer(
    task_id_str: str,
    until_str: str,
    reason: str | None,
    profile: str | None,
    timezone: str | None,
) -> None:
    try:
        cfg = resolve_config(profile_override=profile, tz_override=timezone)
        uow = get_uow(cfg)

        async with uow:
            task = await resolve_task_by_short_id(uow, task_id_str, cfg.profile)

        target_time = _parse_defer_date(until_str, cfg.timezone)

        use_case = make_defer_use_case(cfg)
        cmd = DeferTaskCommand(
            task_id=task.id,
            owner_id=cfg.profile,
            until=target_time,
            reason=reason,
        )

        deferred_task = await use_case.execute(cmd)
        formatted_until = format_dt(deferred_task.deferred_until, cfg.timezone)
        count_str = f"Deferred {deferred_task.deferral_count} time(s) (no rush)"
        tid = short_id(deferred_task.id)

        console.print(
            f"\n[bold medium_purple1]⏸ Task {tid} deferred to"
            f" {formatted_until}.[/bold medium_purple1]"
        )
        console.print(f"  {count_str}\n", style="grey62")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc


def _parse_defer_date(until_str: str, tz_name: str) -> datetime:
    """Parse relative offset or ISO timestamp into timezone-aware UTC datetime."""
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    clean = until_str.strip().lower()

    if clean in ("tomorrow", "+1d", "1d"):
        dt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    elif clean in ("next_week", "+7d", "7d"):
        dt = (now + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
    elif clean.startswith("+") and clean.endswith("h"):
        hours = int(clean[1:-1])
        dt = now + timedelta(hours=hours)
    elif clean.startswith("+") and clean.endswith("d"):
        days = int(clean[1:-1])
        dt = now + timedelta(days=days)
    else:
        dt = datetime.fromisoformat(until_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)

    return dt.astimezone(UTC)
