"""Main CLI entry point for Praxis."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

import typer

from praxis_cli.api_client import PraxisApiClient
from praxis_cli.commands.approvals import approvals_app
from praxis_cli.commands.capture import capture
from praxis_cli.commands.clarify import clarify
from praxis_cli.commands.complete import complete
from praxis_cli.commands.defer import defer
from praxis_cli.commands.do import do
from praxis_cli.commands.doctor import doctor
from praxis_cli.commands.list_tasks import list_tasks
from praxis_cli.commands.reconcile import reconcile
from praxis_cli.commands.show import show
from praxis_cli.commands.status import status
from praxis_cli.commands.today import today
from praxis_cli.commands.version import version_cmd
from praxis_cli.config import resolve_config
from praxis_cli.render import render_launch_screen
from praxis_cli.wiring import make_agenda_use_case

app = typer.Typer(
    name="praxis",
    help="Praxis — personal AI execution partner. Turn commitments into completed work.",
    no_args_is_help=False,
    add_completion=False,
)


async def _launch(profile: str | None = None, api: bool = False) -> None:
    cfg = resolve_config(profile_override=profile)
    is_remote = api or bool(os.getenv("PRAXIS_API_URL"))
    storage_desc = f"API: {cfg.api_url}" if is_remote else f"Local: {cfg.store_path.parent}"
    api_key = os.getenv("NEBIUS_API_KEY")
    ai_status = "Nebius [online]" if api_key else "Offline Fallback (ready)"

    spotlight_item = None
    try:
        if is_remote:
            with PraxisApiClient(cfg.api_url) as client:
                agenda = client.today(owner_id=cfg.profile)
                actionable = agenda.get("actionable") or []
                if actionable and isinstance(actionable, list) and isinstance(actionable[0], dict):
                    spotlight_item = actionable[0]
        else:
            use_case = make_agenda_use_case(cfg)
            local_agenda = await use_case.execute(owner_id=cfg.profile)
            if local_agenda.actionable:
                spotlight_item = local_agenda.actionable[0]
    except Exception:
        spotlight_item = None

    render_launch_screen(
        profile=cfg.profile,
        timezone=cfg.timezone,
        storage_desc=storage_desc,
        ai_status=ai_status,
        spotlight_item=spotlight_item,
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
    api: Annotated[
        bool,
        typer.Option("--api", help="Connect to remote API instead of local storage"),
    ] = False,
) -> None:
    """Praxis CLI root callback: launches visual graphic dashboard when run without command."""
    if ctx.invoked_subcommand is None:
        asyncio.run(_launch(profile=profile, api=api))


# Core obligation workflow commands
app.command(name="launch", help="Display Praxis launch dashboard and immediate focus.")(
    lambda profile=None, api=False: asyncio.run(_launch(profile=profile, api=api))
)
app.command(name="capture", help="Capture a commitment and extract next action.")(capture)
app.command(name="clarify", help="Provide clarification for an ambiguous commitment.")(clarify)
app.command(name="today", help="Show prioritized agenda with #1 next action spotlight.")(today)
app.command(name="list", help="List tasks filtered by lifecycle status.")(list_tasks)
app.command(name="show", help="Display full task detail, attempts, and evidence.")(show)
app.command(name="do", help="Execute the immediate next action for a task.")(do)
app.command(name="reconcile", help="Safely reconcile an uncertain API execution attempt.")(
    reconcile
)
app.command(name="complete", help="Mark a task complete with verified evidence.")(complete)
app.command(name="defer", help="Reschedule a task with zero guilt or shame.")(defer)

# Approvals subcommand group
app.add_typer(approvals_app, name="approvals", help="Review and resolve action approvals.")

# Operational & diagnostic commands
app.command(name="doctor", help="Inspect storage integrity and lock health.")(doctor)
app.command(name="status", help="Overview of active profile tasks and approvals.")(status)
app.command(name="version", help="Print version and runtime platform information.")(version_cmd)


if __name__ == "__main__":
    app()
