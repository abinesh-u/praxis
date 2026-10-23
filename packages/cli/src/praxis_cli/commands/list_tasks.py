"""praxis list — list tasks filtered by status."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from praxis_core.entities.common import TaskStatus
from rich.table import Table
from rich.text import Text

from praxis_cli.config import resolve_config
from praxis_cli.render import STATUS_ICONS, console, render_error, short_id
from praxis_cli.wiring import get_uow


def list_tasks(
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            "-s",
            help=(
                "Filter by status "
                "(planned, in_progress, awaiting_approval, completed, deferred, failed, cancelled)"
            ),
        ),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
) -> None:
    """List tasks belonging to the active profile."""
    asyncio.run(_list_tasks(status, profile))


async def _list_tasks(status_str: str | None, profile: str | None) -> None:
    try:
        cfg = resolve_config(profile_override=profile)
        uow = get_uow(cfg)

        target_status = TaskStatus(status_str.lower()) if status_str else None

        async with uow:
            if target_status:
                tasks = await uow.tasks.list_by_status(target_status, cfg.profile)
            else:
                tasks = await uow.tasks.list_by_owner(cfg.profile)

        if not tasks:
            console.print("  No tasks found.", style="grey62")
            return

        table = Table(show_header=True, header_style="bold grey70", box=None, padding=(0, 2))
        table.add_column("ID", style="grey62", width=10)
        table.add_column("", width=2)
        table.add_column("Status", width=18)
        table.add_column("Title", min_width=30)
        table.add_column("Next Action", style="sky_blue1")

        for t in tasks:
            icon, color, label = STATUS_ICONS.get(t.status, ("?", "grey62", str(t.status)))
            cur_act = t.get_current_next_action()
            action_desc = cur_act.description if cur_act else ""
            table.add_row(
                short_id(t.id),
                Text(icon, style=color),
                Text(label, style=color),
                t.title[:45],
                action_desc[:35],
            )

        console.print(table)
    except ValueError as val_err:
        render_error(Exception(f"Invalid status filter '{status_str}'."))
        raise typer.Exit(1) from val_err
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
