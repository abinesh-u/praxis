"""praxis do — execute the immediate next action for a task."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from praxis_core.use_cases import ExecuteNextActionCommand

from praxis_cli.config import resolve_config
from praxis_cli.render import (
    console,
    render_approval_card,
    render_error,
    short_id,
)
from praxis_cli.runner_adapter import LocalCliAgentRunner
from praxis_cli.wiring import (
    get_uow,
    make_execute_next_action_use_case,
    resolve_task_by_short_id,
)


def do(
    task_id: Annotated[
        str,
        typer.Argument(help="Short ID or UUID of the task to execute"),
    ],
    workspace: Annotated[
        str | None,
        typer.Option("--workspace", "-w", help="Workspace root directory path"),
    ] = None,
    force_retry: Annotated[
        bool,
        typer.Option("--force-retry", help="Force re-attempt if prior run had unknown outcome"),
    ] = False,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
) -> None:
    """Execute the immediate next action for a task with safety and approval gates."""
    asyncio.run(_do(task_id, workspace, force_retry, profile))


async def _do(
    task_id_str: str,
    workspace: str | None,
    force_retry: bool,
    profile: str | None,
) -> None:
    try:
        cfg = resolve_config(profile_override=profile)
        uow = get_uow(cfg)

        async with uow:
            task = await resolve_task_by_short_id(uow, task_id_str, cfg.profile)

            # Check if previous attempt was outcome_unknown
            attempts = await uow.attempts.list_for_task(task.id, cfg.profile)
            has_unknown_outcome = any(a.status == "outcome_unknown" for a in attempts)
            if has_unknown_outcome and not force_retry:
                tid = short_id(task.id)
                console.print(
                    "\n[bold indian_red1]"
                    "⚠️  Previous attempt outcome is UNKNOWN."
                    "[/bold indian_red1]\n"
                    "External side effects may have already occurred on your filesystem/services.\n"
                    "Inspect your workspace to verify whether work was completed:\n"
                    f"  • If complete: [bold white]praxis complete {tid}"
                    ' --note "Verified"[/bold white]\n'
                    f"  • If force retry: [bold white]praxis do {tid} --force-retry[/bold white]\n"
                )
                raise typer.Exit(1)

        runner = LocalCliAgentRunner(uow=uow, force_retry=force_retry)
        use_case = make_execute_next_action_use_case(cfg, runner)

        cmd = ExecuteNextActionCommand(
            task_id=task.id,
            owner_id=cfg.profile,
            workspace_root=workspace,
        )

        result = await use_case.execute(cmd)

        if result.approval_request:
            render_approval_card(result.approval_request, user_tz=cfg.timezone)
        elif result.task.status == "completed":
            tid = short_id(result.task.id)
            console.print(
                f"\n[bold green3]✔ Action completed![/bold green3] Task {tid} is complete.\n"
            )
        elif result.outcome.status == "failed":
            console.print(
                f"\n[bold indian_red1]✖ Action failed:[/bold indian_red1] {result.outcome.error}\n"
            )
            raise typer.Exit(1)
        else:
            console.print(f"\n✔ Action '{result.action.description}' executed.\n", style="green3")
    except typer.Exit:
        raise
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
