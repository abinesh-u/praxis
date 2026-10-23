# Praxis

**Don't just help users organize work. Help them get work done.**

Praxis is a personal AI execution system for people who struggle with task initiation, remembering commitments, prioritization, meetings, and administrative follow-through.

It has two interfaces over one execution system:
- **Praxis CLI** — local-first execution with explicitly authorized workspace access.
- **Praxis Web** — planning and oversight for tasks, deadlines, reminders, approvals, and execution history.

## Principles
1. Execution over organization.
2. Durable task and execution state.
3. Bounded autonomy; consequential actions require approval.
4. Local-first files and least-privilege workspace access.
5. Evidence-based completion.
6. Recoverable workflows, idempotency, and bounded retries.

## Repository structure

```text
praxis/
├── apps/web/                 # Next.js + TypeScript UI
├── services/api/             # FastAPI application boundary
├── packages/cli/             # Typer CLI and local workspace interface
├── packages/core/            # Domain entities, use cases, policies, ports
├── packages/agent-runtime/   # Bounded tool-calling runtime
├── packages/scheduler/       # Durable reminders and recurring workflows
├── packages/integrations/    # Permission-scoped adapters
├── contracts/openapi/        # API contract snapshots
├── infra/docker/             # Local infrastructure
├── infra/scripts/            # Setup and maintenance scripts
├── docs/product/             # Product requirements
├── docs/architecture/        # System architecture and ADRs
├── docs/security/             # Threat and permission model
├── docs/development/         # Engineering workflow
├── tests/contract/
├── tests/e2e/
└── .github/workflows/
```

## MVP
- Natural-language commitment capture, persistent tasks, dependencies, and next actions
- Today view; complete, defer, reschedule, and recovery flows
- CLI capture/list/status and explicitly scoped workspace inspection
- Reminders, approval queue, audit history, durable checkpoints
- One narrow administrative workflow with approval gates

Voice, broad email ingestion, many integrations, multi-agent collaboration, and advanced personalization are out of scope until the core execution loop is reliable.

## Stack
- Web: Next.js, React, TypeScript
- API: Python, FastAPI, Pydantic
- Persistence: PostgreSQL
- CLI: Python, Typer
- Background work: durable scheduler/queue (implementation decision pending)
- Local development: Docker Compose

This is an initial scaffold, not a complete production implementation. Start with `docs/development/local-setup.md` and `docs/architecture/03-system-architecture.md`.

## API-backed vertical slice

The first shared execution slice is available locally through SQLite:

```bash
cp .env.example .env
uv run --package praxis-api uvicorn praxis_api.main:app --reload --port 8000
praxis capture "Send the project update" --api
praxis today --api
praxis complete <task-id> --api --note "Sent in the team channel"
```

The terminal workflow keeps recovery state visible: `praxis today` marks
approval blockers and uncertain attempts, while `praxis show <task-id>` lists
attempt IDs, provider IDs, evidence IDs, and safe recovery guidance. For an
API-backed uncertain attempt, use the read-only reconciliation operation:

```bash
praxis reconcile <task-uuid> <attempt-uuid>
```

Reconciliation checks provider status and never dispatches the original action
again. Do not use `--force-retry` for an uncertain outcome until the external
result has been independently verified.

Set `PRAXIS_API_URL` to point the CLI at another API instance. The API
enforces owner-scoped reads, persists commitments/tasks/audit events, and
creates server-owned human-confirmed evidence for explicit completion. For
protected deployments, configure matching opaque `owner=token` values in
`PRAXIS_AUTH_TOKENS` and set the CLI's `PRAXIS_API_TOKEN`.

The bounded execution endpoint is `POST /tasks/{id}/execute`. It dispatches
only actions with `tool_hint=webhook_post` to `PRAXIS_WEBHOOK_URL`, passing a
provider idempotency key. The provider must return JSON containing
`operation_id` and `status: completed` for verified evidence. Timeouts and
accepted-but-incomplete responses become `outcome_unknown`; idempotent retries
do not blindly resubmit the external side effect.

The provider contract must document idempotency-key retention and duplicate
request behavior. A `status: failed` response is authoritative only when it
also includes `failure_final: true`, meaning the operation did not take effect
or its partial effects are explicitly described. Otherwise Praxis preserves
`outcome_unknown` and requires another read-only reconciliation.

Set `PRAXIS_WEBHOOK_STATUS_URL` when the provider exposes a separate operation
lookup base. Redirects are disabled, private/link-local destinations and URL
credentials are rejected, provider IDs are path-constrained, and
`PRAXIS_WEBHOOK_ALLOWED_HOSTS` can enforce an exact hostname allowlist.
Production deployments should additionally enforce network-level egress
restrictions or a controlled resolver so DNS validation and connection-time
resolution cannot diverge.

Before exposing this path to real users, follow the
[execution release-readiness checklist](docs/development/release-readiness.md),
including a disposable real-provider test and the documented procedure for
unresolved outcomes.
