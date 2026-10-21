# Praxis — Product Requirements Document

## Product summary
Praxis is a personal AI execution partner that turns commitments into completed work. It supports people who struggle with task initiation, remembering obligations, prioritization, meetings, and administrative follow-through.

**Promise:** Don't just help users organize work. Help them get work done.

## Problem
Traditional productivity tools store tasks but leave the user responsible for remembering, prioritizing, starting, and completing them. Praxis targets the gap between intention and action.

## Target user
People who lose track of commitments, feel overwhelmed by administrative work, or struggle to identify the next action and follow through. Praxis is a support tool, not a diagnostic or treatment product.

## MVP requirements
### P0 — Core loop
- Capture commitments in natural language.
- Convert commitments into tasks with actionable next steps and optional due dates.
- Persist tasks and dependencies.
- Provide a focused Today view.
- Support complete, defer, reschedule, and recovery.
- Preserve state across sessions and restarts.

### P0 — Trust and control
- Approval queue for consequential actions.
- Audit trail for actions and outcomes.
- Explicitly selected workspace roots for local file access.
- No unrestricted shell execution by default.
- Distinguish verified completion from proposed or failed actions.

### P1 — Interfaces and workflows
- CLI capture, list/today, detail, status, and approval review.
- Web planning, reminders, approvals, and execution history.
- Durable reminders and recurring tasks.
- In-app notifications before external messaging integrations.
- One narrow administrative workflow with approval gates.

## Key journey
1. User captures a commitment.
2. Praxis clarifies missing essentials only when needed.
3. Praxis stores it and proposes a concrete next action.
4. User sees it in Today and receives timely reminders.
5. Tool execution checks permissions and approval policy.
6. Praxis records evidence and reports completion, failure, or recovery steps.

## Success metrics
- Capture-to-action conversion
- Due-task completion or explicit rescheduling rate
- Reminder usefulness and dismissal rate
- Workflow success, recovery, and duplicate-action rates
- Approval and rejection rates
- Time from capture to first meaningful action
- User-reported reduction in mental overhead

## Non-goals
Voice, broad email ingestion, many integrations, autonomous high-impact actions, multi-agent collaboration, and sophisticated learned personalization.

## Release criteria
Core flows tested; server-side authorization enforced; consequential actions gated by approval; scheduler restart-safe and idempotent; audit records explain outcomes; setup and recovery documented.
