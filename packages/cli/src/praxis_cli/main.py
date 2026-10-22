"""Main CLI entry point for Praxis."""

from __future__ import annotations

import typer

from praxis_cli.commands.approvals import approvals_app
from praxis_cli.commands.capture import capture
from praxis_cli.commands.clarify import clarify
from praxis_cli.commands.complete import complete
from praxis_cli.commands.defer import defer
from praxis_cli.commands.do import do
from praxis_cli.commands.doctor import doctor
from praxis_cli.commands.list_tasks import list_tasks
from praxis_cli.commands.show import show
from praxis_cli.commands.status import status
from praxis_cli.commands.today import today
from praxis_cli.commands.version import version_cmd

app = typer.Typer(
    name="praxis",
    help="Praxis — personal AI execution partner. Turn commitments into completed work.",
    no_args_is_help=True,
    add_completion=False,
)

# Core obligation workflow commands
app.command(name="capture", help="Capture a commitment and extract next action.")(capture)
app.command(name="clarify", help="Provide clarification for an ambiguous commitment.")(clarify)
app.command(name="today", help="Show prioritized agenda with #1 next action spotlight.")(today)
app.command(name="list", help="List tasks filtered by lifecycle status.")(list_tasks)
app.command(name="show", help="Display full task detail, attempts, and evidence.")(show)
app.command(name="do", help="Execute the immediate next action for a task.")(do)
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
