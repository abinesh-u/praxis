"""praxis complete — mark a task completed with human verification evidence."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from praxis_core.entities.evidence import Evidence
from praxis_core.use_cases import CompleteTaskCommand

from praxis_cli.config import resolve_config
from praxis_cli.render import console, render_error, short_id
from praxis_cli.wiring import get_uow, make_complete_use_case, resolve_task_by_short_id


def complete(
    task_id: Annotated[
        str,
        typer.Argument(help="Short ID or UUID of the task to complete"),
    ],
    note: Annotated[
        str | None,
        typer.Option("--note", "-n", help="Verification note or proof of completion"),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
) -> None:
    """Explicitly mark a task complete with recorded verification evidence."""
    asyncio.run(_complete(task_id, note, profile))


async def _complete(task_id_str: str, note: str | None, profile: str | None) -> None:
    try:
        cfg = resolve_config(profile_override=profile)
        uow = get_uow(cfg)

        async with uow:
            task = await resolve_task_by_short_id(uow, task_id_str, cfg.profile)

        confirmation = note or "Verified completion by user via CLI."
        evidence = Evidence.human_confirmed(
            target_task_id=task.id,
            user_identity=f"user:{cfg.profile}",
            confirmation_note=confirmation,
        )

        use_case = make_complete_use_case(cfg)
        cmd = CompleteTaskCommand(
            task_id=task.id,
            owner_id=cfg.profile,
            evidence=evidence,
        )

        completed_task = await use_case.execute(cmd)
        tid = short_id(completed_task.id)
        console.print(f"\n[bold green3]✔ Task {tid} marked COMPLETED.[/bold green3]")
        console.print(f"  Title:    {completed_task.title}")
        console.print(f"  Evidence: {confirmation}\n", style="grey62")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
