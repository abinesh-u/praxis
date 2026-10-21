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
