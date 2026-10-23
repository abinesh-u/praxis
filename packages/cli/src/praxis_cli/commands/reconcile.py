"""praxis reconcile — safely resolve an uncertain API execution attempt."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from praxis_cli.api_client import PraxisApiClient
from praxis_cli.config import resolve_config
from praxis_cli.render import attempt_status_label, console, render_error, short_id


def reconcile(
    task_id: Annotated[str, typer.Argument(help="Task ID or short ID")],
    attempt_id: Annotated[str, typer.Argument(help="Execution attempt ID")],
    profile: Annotated[str | None, typer.Option("--profile", "-p")] = None,
) -> None:
    """Read provider status for an uncertain attempt without dispatching it again."""
    asyncio.run(_reconcile(task_id, attempt_id, profile))


async def _reconcile(task_id: str, attempt_id: str, profile: str | None) -> None:
    try:
        cfg = resolve_config(profile_override=profile)
        with PraxisApiClient(cfg.api_url) as client:
            result = client.reconcile_task(
                task_id,
                owner_id=cfg.profile,
                attempt_id=attempt_id,
            )
        status = result.get("attempt_status") or result.get("outcome_status") or "unknown"
        label, color = attempt_status_label(str(status))
        console.print(f"\n[bold {color}]{label}[/bold {color}] attempt {short_id(attempt_id)}")
        if result.get("provider_request_id"):
            console.print(f"Provider ID: {result['provider_request_id']}")
        if result.get("error"):
            console.print(f"Details: {result['error']}", style="yellow3")
        if status == "outcome_unknown":
            console.print(
                "Provider has not confirmed the outcome. "
                "Reconcile again later; do not retry blindly.",
                style="yellow3",
            )
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
