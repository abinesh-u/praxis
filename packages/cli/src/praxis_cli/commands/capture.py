"""praxis capture — natural language commitment capture command."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from praxis_core.entities.common import SourceChannel
from praxis_core.use_cases import CaptureCommitmentCommand

from praxis_cli.api_client import PraxisApiClient
from praxis_cli.config import resolve_config
from praxis_cli.render import console, render_capture_result, render_error
from praxis_cli.wiring import make_capture_use_case


def capture(
    text: Annotated[
        str,
        typer.Argument(help="What commitment or task needs to be done?"),
    ],
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
    timezone: Annotated[
        str | None,
        typer.Option("--tz", help="Timezone override (e.g. America/New_York)"),
    ] = None,
    key: Annotated[
        str | None,
        typer.Option("--key", "-k", help="Idempotency key for safe retries"),
    ] = None,
    api: Annotated[
        bool,
        typer.Option("--api", help="Use the shared API instead of local JSON storage"),
    ] = False,
) -> None:
    """Capture a natural-language commitment into a structured task with a next action."""
    asyncio.run(_capture(text, profile, timezone, key, api))


async def _capture(
    text: str,
    profile: str | None,
    timezone: str | None,
    key: str | None,
    api: bool,
) -> None:
    try:
        cfg = resolve_config(profile_override=profile, tz_override=timezone)
        if api:
            with PraxisApiClient(cfg.api_url) as client:
                result = client.capture(
                    owner_id=cfg.profile,
                    raw_text=text,
                    source=SourceChannel.CLI.value,
                    timezone=cfg.timezone,
                    idempotency_key=key,
                )
            task = result.get("task")
            if task is None:
                console.print(f"\nClarification needed: {result.get('clarification_prompt')}\n")
            else:
                console.print("\n[bold green3]✔ Captured via Praxis API.[/bold green3]")
                console.print(f"  Task:        {task.get('title')}")
                console.print(f"  ID:          {task.get('id')}")
                action = task.get("current_next_action") or {}
                console.print(f"  Next action: {action.get('description', '')}\n")
            return
        use_case = make_capture_use_case(cfg)
        cmd = CaptureCommitmentCommand(
            owner_id=cfg.profile,
            raw_text=text,
            source=SourceChannel.CLI,
            user_timezone=cfg.timezone,
            idempotency_key=key,
        )
        result = await use_case.execute(cmd)
        render_capture_result(result, user_tz=cfg.timezone)
        if result.clarification_needed:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
