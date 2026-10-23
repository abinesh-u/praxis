"""praxis approvals — review and resolve pending action authorizations."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from praxis_core.use_cases import ResolveApprovalCommand
from rich.table import Table

from praxis_cli.config import resolve_config
from praxis_cli.render import (
    console,
    format_dt,
    render_error,
    short_id,
)
from praxis_cli.wiring import (
    get_uow,
    make_resolve_approval_use_case,
    resolve_approval_by_short_id,
)

approvals_app = typer.Typer(
    name="approvals",
    help="Review and resolve pending tool execution approvals.",
    no_args_is_help=True,
)


@approvals_app.command(name="list")
def list_approvals(
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
    timezone: Annotated[
        str | None,
        typer.Option("--tz", help="Timezone override"),
    ] = None,
) -> None:
    """List all pending action authorization requests awaiting human decision."""
    asyncio.run(_list_approvals(profile, timezone))


async def _list_approvals(profile: str | None, timezone: str | None) -> None:
    try:
        cfg = resolve_config(profile_override=profile, tz_override=timezone)
        uow = get_uow(cfg)

        async with uow:
            pending = await uow.approvals.list_pending(cfg.profile)

        if not pending:
            console.print("  ✔ No pending approvals. Everything is clear.", style="green3")
            return

        table = Table(
            show_header=True,
            header_style="bold yellow3",
            box=None,
            padding=(0, 2),
        )
        table.add_column("Request ID", style="bold white", width=12)
        table.add_column("Task ID", style="grey62", width=10)
        table.add_column("Risk", style="yellow3", width=14)
        table.add_column("Tool", style="sky_blue1", min_width=20)
        table.add_column("Arguments", min_width=20)
        table.add_column("Expires", style="grey62", width=18)

        for req in pending:
            table.add_row(
                short_id(req.id),
                short_id(req.task_id),
                req.risk_level.value.upper(),
                req.action.tool_name,
                str(req.action.canonical_args)[:35],
                format_dt(req.expires_at, cfg.timezone),
            )

        console.print(table)
        console.print("\nRun [bold white]praxis approvals approve <id>[/bold white] to authorize.")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc


@approvals_app.command(name="approve")
def approve(
    approval_id: Annotated[
        str,
        typer.Argument(help="Short ID or UUID of the approval request to grant"),
    ],
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
) -> None:
    """Approve a consequential action, granting permission for execution."""
    asyncio.run(_resolve(approval_id, "approve", None, False, profile))


@approvals_app.command(name="reject")
def reject(
    approval_id: Annotated[
        str,
        typer.Argument(help="Short ID or UUID of the approval request to reject"),
    ],
    reason: Annotated[
        str | None,
        typer.Option("--reason", "-r", help="Reason for rejection"),
    ] = None,
    fatal: Annotated[
        bool,
        typer.Option("--fatal", help="Mark the parent task as permanently failed"),
    ] = False,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
) -> None:
    """Reject a consequential action authorization request."""
    asyncio.run(_resolve(approval_id, "reject", reason, fatal, profile))


async def _resolve(
    approval_id_str: str,
    decision: str,
    reason: str | None,
    fatal: bool,
    profile: str | None,
) -> None:
    try:
        cfg = resolve_config(profile_override=profile)
        uow = get_uow(cfg)

        async with uow:
            approval = await resolve_approval_by_short_id(uow, approval_id_str, cfg.profile)

        use_case = make_resolve_approval_use_case(cfg)
        cmd = ResolveApprovalCommand(
            approval_id=approval.id,
            owner_id=cfg.profile,
            decision=decision,
            rejection_reason=reason,
            fatal_rejection=fatal,
        )
        res = await use_case.execute(cmd)

        aid = short_id(res.approval.id)
        tid = short_id(res.task.id)
        if decision == "approve":
            console.print(f"\n[bold green3]✔ Approval granted for request {aid}.[/bold green3]")
            console.print(f"Task {tid} is unblocked. Run: 'praxis do {tid}'.\n")
        else:
            console.print(
                f"\n[bold indian_red1]✖ Action rejected for request {aid}.[/bold indian_red1]"
            )
            console.print(f"Task status is now '{res.task.status.value}'.\n", style="grey62")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
