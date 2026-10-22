"""Rich rendering helpers for calm, low-friction terminal output."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from praxis_core.entities.approval import ApprovalRequest
from praxis_core.entities.common import Priority, TaskStatus
from praxis_core.entities.task import Task
from praxis_core.use_cases.capture_commitment import CaptureCommitmentResult
from praxis_core.use_cases.get_daily_agenda import AgendaTaskItem
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# Calm, low-stimulation color palette
COLORS = {
    "focus": "sky_blue1",  # Active / immediate spotlight
    "success": "green3",  # Verified evidence / completed
    "warning": "yellow3",  # Approvals waiting
    "error": "indian_red1",  # Failures / urgent (never shaming)
    "dim": "grey62",  # Timestamps & metadata
    "deferred": "medium_purple1",  # Guilt-free deferral
}

STATUS_ICONS = {
    TaskStatus.PLANNED: ("◯", COLORS["dim"], "Planned"),
    TaskStatus.IN_PROGRESS: ("▶", COLORS["focus"], "In Progress"),
    TaskStatus.AWAITING_APPROVAL: ("⏳", COLORS["warning"], "Awaiting Approval"),
    TaskStatus.COMPLETED: ("✔", COLORS["success"], "Completed"),
    TaskStatus.DEFERRED: ("⏸", COLORS["deferred"], "Deferred"),
    TaskStatus.FAILED: ("✖", COLORS["error"], "Needs Attention"),
    TaskStatus.CANCELLED: ("—", COLORS["dim"], "Cancelled"),
}

PRIORITY_STYLES = {
    Priority.URGENT: ("⚡ Urgent", COLORS["error"]),
    Priority.IMPORTANT: ("● Important", COLORS["warning"]),
    Priority.ROUTINE: ("○ Routine", COLORS["dim"]),
}


def short_id(uid: UUID | str) -> str:
    """Format 8-character prefix of UUID for terminal display."""
    return str(uid).replace("-", "").lower()[:8]


def format_dt(dt: datetime | None, user_tz: str = "UTC") -> str:
    """Format timestamp localized to user timezone."""
    if dt is None:
        return "No date"
    try:
        local_dt = dt.astimezone(ZoneInfo(user_tz))
        return local_dt.strftime("%b %d, %I:%M %p")
    except Exception:
        return dt.strftime("%b %d, %I:%M %p")


def render_spotlight(item: AgendaTaskItem, user_tz: str = "UTC") -> None:
    """Render the single immediate next action in a prominent calm panel."""
    task = item.task
    action = item.current_next_action

    pri_label, pri_style = PRIORITY_STYLES.get(task.priority, ("", COLORS["dim"]))
    due_str = format_dt(task.due_date, user_tz) if task.due_date else "No deadline"

    content = Text()
    content.append(f"{task.title}\n", style="bold white")
    if action:
        content.append(f"Next Action: {action.description}\n", style=f"bold {COLORS['focus']}")
    content.append(f"{pri_label}  •  Due: {due_str}", style=pri_style)

    if task.deferred_until:
        defer_str = format_dt(task.deferred_until, user_tz)
        content.append(f"  •  Deferred until: {defer_str}", style=COLORS["deferred"])

    panel = Panel(
        content,
        title="[bold sky_blue1]🎯 RIGHT NOW[/bold sky_blue1]",
        subtitle="[grey62]Run 'praxis do <id>' to execute with agent assistance[/grey62]",
        border_style=COLORS["focus"],
        padding=(1, 2),
    )
    console.print(panel)


def render_agenda_table(
    actionable: list[AgendaTaskItem],
    waiting: list[AgendaTaskItem],
    user_tz: str = "UTC",
) -> None:
    """Render actionable and waiting queues as a clean, scannable table."""
    if not actionable and not waiting:
        console.print("  ✨ No active tasks on your agenda.", style=COLORS["dim"])
        return

    table = Table(
        show_header=True,
        header_style="bold grey70",
        box=None,
        padding=(0, 2),
        collapse_padding=True,
    )
    table.add_column("ID", style=COLORS["dim"], width=10)
    table.add_column("", width=2)
    table.add_column("Task", min_width=28)
    table.add_column("Next Step / State", style=COLORS["focus"], min_width=25)
    table.add_column("Due / Info", style=COLORS["dim"], width=18)

    for item in actionable:
        icon, style, _ = STATUS_ICONS.get(item.task.status, ("?", COLORS["dim"], ""))
        due = format_dt(item.task.due_date, user_tz) if item.task.due_date else ""
        step = item.current_next_action.description if item.current_next_action else "Ready"
        table.add_row(
            short_id(item.task.id),
            Text(icon, style=style),
            item.task.title[:45],
            step[:40],
            due,
        )

    for item in waiting:
        icon, style, _ = STATUS_ICONS.get(item.task.status, ("?", COLORS["dim"], ""))
        reason = item.waiting_reason or "Waiting on dependencies"
        table.add_row(
            short_id(item.task.id),
            Text(icon, style=style),
            Text(item.task.title[:45], style=COLORS["dim"]),
            Text(reason[:40], style=COLORS["dim"]),
            "",
        )

    console.print(table)


def render_capture_result(result: CaptureCommitmentResult, user_tz: str = "UTC") -> None:
    """Render confirmation panel for captured natural language commitment."""
    if result.clarification_needed:
        prompt_txt = result.clarification_prompt or "Please provide additional context."
        cid = short_id(result.commitment.id)
        msg = Text()
        msg.append("⚠️ Commitment captured, but details are ambiguous:\n\n", style=COLORS["warning"])
        msg.append(f"{prompt_txt}\n\n", style="white")
        msg.append(f"Run 'praxis clarify {cid} \"<details>\"' to update.", style=COLORS["dim"])
        panel = Panel(
            msg,
            title="[yellow3]Clarification Needed[/yellow3]",
            border_style=COLORS["warning"],
        )
        console.print(panel)
        return

    task = result.task
    if not task:
        console.print("✔ Commitment recorded.", style=COLORS["success"])
        return

    content = Text()
    content.append("✔ Commitment captured & scheduled:\n\n", style="bold green3")
    content.append(f"  Title:       {task.title}\n", style="bold white")
    if result.next_action:
        content.append(f"  Next Action: {result.next_action.description}\n", style=COLORS["focus"])
    if task.due_date:
        content.append(f"  Deadline:    {format_dt(task.due_date, user_tz)}\n", style=COLORS["dim"])
    content.append(f"  Priority:    {task.priority.value.title()}\n", style=COLORS["dim"])
    content.append(f"\n  Short ID:    {short_id(task.id)}", style=f"bold {COLORS['focus']}")

    console.print(Panel(content, border_style=COLORS["success"], padding=(1, 2)))


def render_task_detail(task: Task, user_tz: str = "UTC") -> None:
    """Render full detail view for a task."""
    icon, status_color, status_label = STATUS_ICONS.get(task.status, ("?", "", str(task.status)))
    pri_label, pri_color = PRIORITY_STYLES.get(task.priority, ("", ""))

    content = Text()
    content.append(f"{task.title}\n", style="bold white")
    if task.description:
        content.append(f"{task.description}\n\n", style="grey70")

    content.append("Status:      ", style=COLORS["dim"])
    content.append(f"{icon} {status_label}\n", style=status_color)
    content.append(f"Priority:    {pri_label}\n", style=pri_color)
    content.append(f"Due Date:    {format_dt(task.due_date, user_tz)}\n", style=COLORS["dim"])

    if task.deferred_until:
        d_str = format_dt(task.deferred_until, user_tz)
        content.append(
            f"Deferred:    Until {d_str} (count: {task.deferral_count})\n",
            style=COLORS["deferred"],
        )

    if task.failure_reason:
        content.append(f"Failure:     {task.failure_reason}\n", style=COLORS["error"])
        if task.recovery_suggestion:
            content.append(f"Recovery:    {task.recovery_suggestion}\n", style=COLORS["focus"])

    if task.next_actions:
        content.append("\nNext Actions:\n", style="bold white")
        for i, a in enumerate(task.next_actions, 1):
            done_icon = "✔" if a.completed else "◯"
            done_color = COLORS["success"] if a.completed else COLORS["dim"]
            content.append(f"  {i}. [{done_icon}] {a.description}", style=done_color)
            if a.tool_hint:
                content.append(f" (tool: {a.tool_hint})", style=COLORS["dim"])
            content.append("\n")

    if task.dependencies:
        content.append("\nDependencies:\n", style="bold white")
        for d in task.dependencies:
            dep_id = short_id(d.depends_on_task_id)
            content.append(f"  • {d.dependency_type.value}: Task {dep_id}\n", style=COLORS["dim"])

    panel = Panel(
        content,
        title=f"[bold sky_blue1]Task {short_id(task.id)}[/bold sky_blue1]",
        border_style=COLORS["focus"],
        padding=(1, 2),
    )
    console.print(panel)


def render_approval_card(approval: ApprovalRequest, user_tz: str = "UTC") -> None:
    """Render consequential action approval review card."""
    content = Text()
    content.append("⚠️  CONSEQUENTIAL ACTION REQUIRES APPROVAL\n\n", style="bold yellow3")
    content.append(f"Request ID:    {short_id(approval.id)}\n", style="bold white")
    content.append(f"Task ID:       {short_id(approval.task_id)}\n", style=COLORS["dim"])
    content.append(f"Tool Name:     {approval.action.tool_name}\n", style=COLORS["focus"])
    content.append(f"Arguments:     {approval.action.canonical_args}\n", style="white")
    content.append(f"Risk Level:    {approval.risk_level.value.upper()}\n", style=COLORS["warning"])
    content.append(f"Justification: {approval.justification}\n", style=COLORS["dim"])
    exp_str = format_dt(approval.expires_at, user_tz)
    content.append(f"Expires:       {exp_str}\n", style=COLORS["dim"])
    content.append(f"Action Hash:   {approval.action_fingerprint[:16]}...\n\n", style=COLORS["dim"])
    content.append(
        f"Approve: praxis approvals approve {short_id(approval.id)}\n"
        f"Reject:  praxis approvals reject {short_id(approval.id)}",
        style=f"bold {COLORS['focus']}",
    )

    panel = Panel(content, border_style=COLORS["warning"], padding=(1, 2))
    console.print(panel)


def render_error(err: Exception) -> None:
    """Render friendly error message without traceback."""
    msg = Text()
    msg.append("Error: ", style="bold indian_red1")
    msg.append(str(err), style="white")
    console.print(msg)
