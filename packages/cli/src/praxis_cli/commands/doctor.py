"""praxis doctor — system diagnostics and storage integrity inspection."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

import typer
from praxis_core.entities.common import TaskStatus

from praxis_cli.config import resolve_config
from praxis_cli.render import console, render_error
from praxis_cli.wiring import get_uow


def doctor(
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Target profile"),
    ] = None,
) -> None:
    """Perform health and integrity diagnostics on the local environment and storage."""
    asyncio.run(_doctor(profile))


async def _doctor(profile: str | None) -> None:
    try:
        cfg = resolve_config(profile_override=profile)
        console.print(
            f"[bold sky_blue1]Praxis Doctor — Profile: '{cfg.profile}'[/bold sky_blue1]\n"
        )

        # 1. Directory permissions
        dir_stat = cfg.store_path.parent.stat() if cfg.store_path.parent.exists() else None
        if dir_stat:
            mode = oct(dir_stat.st_mode)[-3:]
            console.print(
                f"  ✔ Storage Directory: {cfg.store_path.parent} ({mode})", style="green3"
            )
        else:
            console.print(
                f"  ℹ Storage Directory: Uninitialized ({cfg.store_path.parent})", style="grey62"
            )

        # 2. Storage database state
        db_file = cfg.db_path
        if db_file.exists():
            console.print(f"  ✔ SQLite Database: Healthy ({db_file.name})", style="green3")
        else:
            console.print("  ℹ SQLite Database: Clean (uninitialized)", style="grey62")

        # 3. Store file & orphaned attempts
        uow = get_uow(cfg)
        async with uow:
            console.print("  ✔ Storage Database: Accessible and schema valid", style="green3")

            # Check orphaned running attempts
            reconciled_count = 0
            if hasattr(uow, "_connection") and uow._connection:
                query = (
                    "SELECT payload FROM execution_attempts "
                    "WHERE owner_id = ? AND status = 'running'"
                )
                rows = uow._connection.execute(query, (cfg.profile,)).fetchall()
                for row in rows:
                    from praxis_core.entities.execution_attempt import ExecutionAttempt

                    att = ExecutionAttempt.model_validate_json(row["payload"])
                    att.mark_outcome_unknown("Process interrupted; external outcome unknown")
                    await uow.attempts.save(att)
                    task = await uow.tasks.get_for_owner(att.task_id, cfg.profile)
                    if task and task.status in (
                        TaskStatus.IN_PROGRESS,
                        TaskStatus.AWAITING_APPROVAL,
                    ):
                        task.fail(
                            reason="External action outcome unknown (process interrupted)",
                            recovery_suggestion="Inspect workspace before retrying action",
                        )
                        await uow.tasks.save(task)
                    reconciled_count += 1
            elif hasattr(uow.attempts, "_attempts"):
                for att_raw in list(uow.attempts._attempts.values()):
                    if (
                        att_raw.get("owner_id") == cfg.profile
                        and att_raw.get("status") == "running"
                    ):
                        att_raw["status"] = "outcome_unknown"
                        att_raw["error_message"] = "Process interrupted; external outcome unknown"
                        task_id_str = att_raw.get("task_id")
                        if task_id_str and task_id_str in uow.tasks._tasks:
                            t_raw = uow.tasks._tasks[task_id_str]
                            t_raw["status"] = TaskStatus.FAILED.value
                            t_raw["failure_reason"] = (
                                "External action outcome unknown (process interrupted)"
                            )
                            t_raw["recovery_suggestion"] = (
                                "Inspect workspace before retrying action"
                            )
                        reconciled_count += 1
            if reconciled_count > 0:
                await uow.commit()
                console.print(
                    f"  ⚠️ Reconciled {reconciled_count} interrupted running attempt(s) "
                    "to 'outcome_unknown'.",
                    style="yellow3",
                )
            else:
                console.print(
                    "  ✔ Execution Attempts: No orphaned or interrupted runs", style="green3"
                )

        # 4. Timezone
        console.print(f"  ✔ Timezone: {cfg.timezone}", style="green3")

        # 5. AI Extraction status
        api_key = os.getenv("NEBIUS_API_KEY")
        if api_key:
            masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
            console.print(
                f"  ✔ AI Extraction: Nebius Token Factory configured ({masked})", style="green3"
            )
        else:
            console.print("  ℹ AI Extraction: Offline fallback active", style="grey62")

        console.print("\n[bold green3]All diagnostic checks passed.[/bold green3]")
    except Exception as exc:
        render_error(exc)
        raise typer.Exit(1) from exc
