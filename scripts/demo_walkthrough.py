#!/usr/bin/env python3
"""Praxis Demo Walkthrough & Pre-Flight Helper for Nebius Hackathon.

Provides:
  --check      Verify Nebius Token Factory inference, database health, API & Web reachability.
  --seed       Seed a pristine demo scenario (task, approval, quarantined skill).
  --reset      Reset all demo records in SQLite and skills storage.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

# Auto-load .env
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
WEB_URL = os.getenv("WEB_BASE_URL", "http://localhost:3000")
DB_URL = os.getenv("DATABASE_URL", "sqlite:///praxis.db")
SKILLS_DIR = Path(os.getenv("PRAXIS_SKILLS_DIR", "./.praxis/skills")).resolve()


def check_status() -> bool:
    """Check connectivity to Nebius, local API, Web UI, and Database."""
    console.print("\n[bold cyan]═══ Praxis Pre-Flight System Check ═══[/bold cyan]\n")
    all_ok = True

    # 1. Nebius Token Factory
    api_key = os.getenv("NEBIUS_API_KEY") or os.getenv("MODEL_API_KEY")
    if api_key:
        masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        try:
            from praxis_core.models.config import ModelConfig
            from praxis_core.models.providers.base import NormalizedCompletionRequest
            from praxis_core.models.providers.nebius import NebiusTokenFactoryAdapter

            cfg = ModelConfig(
                key="nemotron-3.5-lightning",
                display_name="Nemotron 3.5 Lightning",
                provider="nebius",
                model_id="nvidia/Nemotron-3_5-Lightning",
                temperature=0.1,
                max_output_tokens=30,
            )
            adapter = NebiusTokenFactoryAdapter(config=cfg, api_key=api_key)
            t0 = time.monotonic()
            resp = adapter.invoke(
                NormalizedCompletionRequest(
                    messages=[{"role": "user", "content": "Respond with: PONG"}],
                    max_tokens=10,
                )
            )
            dt = time.monotonic() - t0
            console.print(
                f"  ✔ [bold green]Nebius Token Factory:[/bold green] Online ({masked}) — "
                f"Model: {resp.model} ({dt:.2f}s)"
            )
        except Exception as err:
            console.print(f"  ✖ [bold red]Nebius Token Factory Error:[/bold red] {err}")
            all_ok = False
    else:
        console.print(
            "  ℹ [bold yellow]Nebius Token Factory:[/bold yellow] "
            "No API key found in .env (offline fallback active)"
        )

    # 2. Local Backend API
    try:
        resp = httpx.get(f"{API_URL}/health", timeout=3.0)
        if resp.status_code == 200:
            console.print(f"  ✔ [bold green]FastAPI Backend:[/bold green] Reachable at {API_URL}")
        else:
            console.print(
                f"  ✖ [bold red]FastAPI Backend:[/bold red] Returned HTTP {resp.status_code}"
            )
            all_ok = False
    except Exception:
        console.print(
            f"  ✖ [bold red]FastAPI Backend:[/bold red] Not running at {API_URL}. "
            "Start with: make api-dev"
        )
        all_ok = False

    # 3. Next.js Web UI
    try:
        resp = httpx.get(WEB_URL, timeout=3.0)
        if resp.status_code == 200:
            console.print(f"  ✔ [bold green]Next.js Web UI:[/bold green] Reachable at {WEB_URL}")
        else:
            console.print(
                f"  ✖ [bold red]Next.js Web UI:[/bold red] Returned HTTP {resp.status_code}"
            )
            all_ok = False
    except Exception:
        console.print(
            f"  ℹ [bold yellow]Next.js Web UI:[/bold yellow] Not running at {WEB_URL}. "
            "Start with: make web-dev"
        )

    # 4. Storage & Skills Directory
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    count = len(list(SKILLS_DIR.glob("*.json")))
    console.print(
        f"  ✔ [bold green]Skills Storage:[/bold green] {SKILLS_DIR} ({count} skills present)"
    )

    console.print()
    return all_ok


def seed_demo_scenario() -> None:
    """Seed an authentic, judge-ready end-to-end scenario into Praxis."""
    import asyncio

    from praxis_agent_runtime.skills.models import Skill
    from praxis_agent_runtime.skills.skill_store import SkillStore
    from praxis_core.entities.approval import ActionSpecification, ApprovalRequest
    from praxis_core.entities.common import ActionRiskLevel, Priority, TaskStatus
    from praxis_core.entities.execution_attempt import ExecutionAttempt
    from praxis_core.entities.next_action import NextAction
    from praxis_core.entities.task import Task
    from praxis_core.persistence.sqlite import SQLiteUnitOfWork

    console.print("\n[bold cyan]Seeding Judge-Ready Demo Scenario...[/bold cyan]")

    owner_id = "default_user"
    now = datetime.now(UTC)

    # 1. Completed Task with authoritative machine evidence
    task_id = uuid4()
    evidence_id = uuid4()
    attempt_id = uuid4()
    short_attempt = str(attempt_id).replace("-", "")[:12]
    evidence_hash = hashlib.sha256(f"{attempt_id}:{evidence_id}".encode()).hexdigest()[:16]

    completed_task = Task(
        id=task_id,
        owner_id=owner_id,
        title="Automate JWT Token Verification Protocol",
        description="Verify expired token revocation and multi-tenant security perimeter.",
        status=TaskStatus.COMPLETED,
        priority=Priority.IMPORTANT,
        due_date=now - timedelta(hours=2),
        completed_at=now - timedelta(minutes=45),
        created_at=now - timedelta(hours=3),
        updated_at=now - timedelta(minutes=45),
    )

    completed_action_id = uuid4()
    attempt = ExecutionAttempt(
        id=attempt_id,
        owner_id=owner_id,
        task_id=task_id,
        action_id=completed_action_id,
        idempotency_key=f"idem_{uuid4().hex[:16]}",
        status="completed",
        started_at=now - timedelta(minutes=50),
        completed_at=now - timedelta(minutes=45),
        evidence_id=evidence_id,
    )

    # 2. Actionable Today Task
    active_task_id = uuid4()
    active_action_id = uuid4()

    active_action = NextAction(
        id=active_action_id,
        task_id=active_task_id,
        owner_id=owner_id,
        description="Run security regression scan on token revocation endpoint",
        tool_hint="fs_read_file",
        tool_args_hint={"path": "services/api/src/praxis_api/auth.py"},
        risk_level=ActionRiskLevel.READ_ONLY,
        sort_order=0,
    )

    active_task = Task(
        id=active_task_id,
        owner_id=owner_id,
        title="Verify Token Revocation Security Perimeter",
        description="Run automated adversarial validation against expired bearer tokens.",
        status=TaskStatus.PLANNED,
        priority=Priority.URGENT,
        due_date=now + timedelta(days=1),
        current_next_action=active_action,
        created_at=now - timedelta(hours=1),
        updated_at=now,
    )

    # 3. Action Approval Request
    action_spec = ActionSpecification(
        tool_name="fs_read_file",
        canonical_args={"path": "services/api/src/praxis_api/auth.py"},
        task_id=active_task_id,
    )
    approval, _ = ApprovalRequest.create(
        owner_id=owner_id,
        task_id=active_task_id,
        action=action_spec,
        risk_level=ActionRiskLevel.CONSEQUENTIAL,
        justification="Execute workspace inspection and token validation on auth.py",
        expires_in_seconds=86400,
        now=now,
    )

    # Save to SQLite
    uow = SQLiteUnitOfWork(DB_URL)

    async def _persist():
        async with uow:
            await uow.tasks.save(completed_task)
            await uow.attempts.save(attempt)
            await uow.tasks.save(active_task)
            await uow.approvals.save(approval)
            await uow.commit()

    asyncio.run(_persist())
    console.print(
        "  ✔ [bold green]SQLite Database:[/bold green] Persisted tasks, attempts, and approvals."
    )

    # 4. Quarantined Candidate Skill in SkillStore
    store = SkillStore(SKILLS_DIR)
    candidate_skill = Skill(
        id=f"candidate_att_{short_attempt}",
        name=f"candidate_att_{short_attempt}",
        description="Procedural verification routine for JWT token expiry and tenant perimeter.",
        triggers=["jwt", "token_expiry", "auth_verification"],
        required_tools=["fs_read_file", "fs_list_dir"],
        instructions=(
            "1. Inspect services/api/src/praxis_api/auth.py for token expiration handling.\n"
            "2. Verify that resolve_operator() enforces fail-closed authentication in production.\n"
            "3. Execute test suite against invalid bearer credentials and verify 401 response."
        ),
        status="candidate",
        provenance={
            "attempt_id": str(attempt_id),
            "task_id": str(task_id),
            "owner_id": owner_id,
            "evidence_hash": evidence_hash,
            "created_at": now.isoformat(),
        },
    )

    store.save(candidate_skill)
    console.print(
        f"  ✔ [bold green]Quarantined Candidate Skill:[/bold green] "
        f"Created '{candidate_skill.name}' in {SKILLS_DIR}"
    )

    panel_text = (
        "[bold white]Demo Scenario Successfully Seeded![/bold white]\n\n"
        "• [cyan]Today Agenda:[/cyan] 1 urgent actionable task ('Verify Token Revocation')\n"
        "• [cyan]Approvals Tab (3):[/cyan] 1 pending consequential authorization request\n"
        "• [cyan]Skills Tab (4):[/cyan] 1 quarantined candidate skill ready for M8 promotion\n\n"
        f"[bold yellow]Next Step:[/bold yellow] Open [underline]{WEB_URL}[/underline] "
        "and follow [italic]docs/DEMO_VIDEO_SCRIPT.md[/italic]."
    )
    console.print(Panel(panel_text, border_style="green"))


def reset_demo_scenario() -> None:
    """Reset all records for clean replay."""
    import sqlite3

    db_path = DB_URL.replace("sqlite:///", "")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for tbl in ["execution_attempts", "approvals", "tasks", "commitments", "audit_events"]:
            with contextlib.suppress(Exception):
                cur.execute(f"DELETE FROM {tbl}")
        conn.commit()
        conn.close()
        console.print(f"  ✔ [bold green]Database Cleared:[/bold green] {db_path}")

    # Remove generated skills
    if SKILLS_DIR.exists():
        for p in SKILLS_DIR.glob("*.json"):
            p.unlink()
        console.print(f"  ✔ [bold green]Skills Directory Cleared:[/bold green] {SKILLS_DIR}")

    console.print("[bold yellow]State reset successfully.[/bold yellow]\n")


def main():
    parser = argparse.ArgumentParser(description="Praxis Demo Walkthrough & Pre-Flight Helper")
    parser.add_argument("--check", action="store_true", help="Run pre-flight checks")
    parser.add_argument("--seed", action="store_true", help="Seed a judge-ready demo scenario")
    parser.add_argument("--reset", action="store_true", help="Reset all demo records")
    args = parser.parse_args()

    if args.check:
        check_status()
    elif args.seed:
        seed_demo_scenario()
    elif args.reset:
        reset_demo_scenario()
    else:
        check_status()
        console.print("\n[bold]Select an action:[/bold]")
        console.print("  [cyan]1[/cyan]. Seed pristine demo data (`--seed`)")
        console.print("  [cyan]2[/cyan]. Reset all demo data (`--reset`)")
        console.print("  [cyan]3[/cyan]. Exit")
        choice = input("\nEnter choice (1-3): ").strip()
        if choice == "1":
            seed_demo_scenario()
        elif choice == "2":
            reset_demo_scenario()
        else:
            console.print("Exiting.")


if __name__ == "__main__":
    main()
