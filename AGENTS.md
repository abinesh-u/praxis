# AGENTS.md --- Praxis

## 1. Project mission

**Praxis is a personal AI execution partner, not a general-purpose
chatbot or another task manager.**

Its promise: **"You don't need another app to manage your tasks. You
need help actually doing them."**

Praxis helps people remember commitments, overcome task-initiation
friction, take the next concrete step, handle approved administrative
work, and recover when plans fail. Design for people who struggle with
prospective memory, executive overhead, task initiation, and
follow-through. Do not diagnose users or present Praxis as a medical
treatment.

## 2. Product principles

-   **Execution over conversation:** Optimize for completed, verified
    outcomes---not long chats or generated plans.
-   **One reliable loop first:** Capture → persist → clarify
    dependencies → identify the next action → remind → request approval
    where needed → execute → verify → recover.
-   **Reduce cognitive load:** Make the next step obvious. Keep
    interaction calm, concise, and low-friction.
-   **Durable state:** Important commitments and workflow state must
    survive restarts, device changes, and worker failures.
-   **User agency by default:** Explain what Praxis intends to do.
    Require approval for consequential actions unless an explicitly
    scoped, revocable permission covers them.
-   **Evidence over assumptions:** Verify outcomes using observable
    evidence. Never claim an action succeeded merely because a tool was
    called.
-   **Bounded autonomy:** Use explicit limits, timeouts, retry policies,
    budgets, and escalation paths.
-   **Privacy and least privilege:** Request only the permissions and
    data necessary for the current capability.
-   **Recoverability:** Make failures visible and actionable; preserve
    context so the user can resume without starting over.

## 3. MVP scope and priorities

The MVP must prove one end-to-end execution loop before expanding
breadth.

### Prioritize

1.  Natural-language capture of a commitment or task.
2.  Persistent records for commitments, deadlines, dependencies, status,
    and relevant context.
3.  A clear, actionable next step.
4.  Reliable reminders and scheduling.
5.  Approval-gated actions.
6.  Outcome verification, failure handling, and recovery.
7.  A web interface and CLI that use the same underlying execution
    system.
8.  Telegram as the first external gateway, alongside web and CLI.

### Do not prematurely build

-   Broad integrations across every platform.
-   Unbounded autonomous agents or unrestricted shell/file access.
-   Irreversible actions without explicit confirmation.
-   A noisy, notification-heavy experience.
-   A generic assistant that merely answers questions.
-   Complex multi-agent infrastructure without a demonstrated need.
-   Medical diagnosis, treatment claims, or assumptions about a user's
    condition.

Slack, Discord, email, and SMS are future gateway targets; do not treat
them as MVP requirements unless the product owner changes scope.

## 4. Product surfaces and system boundaries

Praxis is one execution system exposed through multiple interfaces.

-   **Web app:** Planning, task and commitment management, scheduling,
    reminders, approvals, execution history, and recovery.
-   **CLI:** Fast capture and execution workflows for technical users.
    It may access local files and run local commands only through
    explicit, scoped permissions and safe execution policies.
-   **Gateway adapters:** Translate platform-specific messages and
    events into a common Praxis command/event format. Telegram is the
    initial external gateway.
-   **Core/domain layer:** Owns commitments, tasks, policies, workflow
    state, permissions, scheduling intent, and execution lifecycle.
    Business rules must not live only in a UI or gateway.
-   **Execution/tool layer:** Performs bounded actions through explicit
    capabilities, records results, and supports verification and
    recovery.
-   **Scheduler/worker:** Runs durable scheduled jobs and reminders
    independently of a user's active session.

Web, CLI, and gateways must call shared application/domain services
rather than implement separate business logic.

## 5. Architecture direction

The current proposed stack is:

-   **Web:** React/Next.js with TypeScript.
-   **API/backend:** Python with FastAPI.
-   **Persistence:** PostgreSQL.
-   **Scheduling/execution:** A persistent scheduler and worker/queue
    design, with database-backed job claiming where appropriate.
-   **AI:** A tool-calling model operating inside a bounded control
    loop.

Treat these as the current architectural direction, not permission to
introduce every technology immediately. Before changing or adding a
framework, inspect the repository and its existing decisions. Prefer the
smallest architecture that meets the requirements.

### Modular design

Keep modules cohesive and boundaries explicit. A reasonable logical
decomposition is:

-   `apps/web` --- web interface.
-   `apps/cli` --- command-line interface.
-   `apps/api` --- HTTP/API entry point.
-   `packages/` or `src/` --- shared contracts and domain/application
    logic, adapted to the actual language and repository layout.
-   `services/worker` --- scheduled and asynchronous execution, if
    separated operationally.
-   `integrations/` --- gateway and external-service adapters.
-   `docs/` --- product and architecture documentation.
-   `tests/` --- unit, integration, and end-to-end tests, colocated
    where the repository convention is stronger.

This is a suggested logical layout, not a mandate to create empty
packages. Follow the repository's established structure and introduce
modules only when they have real responsibilities.

## 6. Scheduling and background work

Scheduled work is an **application-level durable process**, not a
dependency on the host operating system's cron configuration.

The scheduling design must account for:

-   Persisted jobs and schedules.
-   Time zones and daylight-saving transitions.
-   Retries with backoff and bounded attempts.
-   Idempotency and duplicate delivery.
-   Concurrency control and atomic job claiming.
-   Missed-run and worker-restart behavior.
-   Cancellation, rescheduling, and job state transitions.
-   Observability and actionable failure states.

Do not rely on an in-memory timer as the only record of important
scheduled work. A job may be delivered more than once; handlers must be
idempotent or use an explicit deduplication strategy.

## 7. Agent and tool-execution rules

-   Use a bounded agent loop with explicit stop conditions and a maximum
    number of tool calls/steps.
-   Validate tool inputs against typed schemas before execution.
-   Enforce authorization in the backend/tool boundary, not only in the
    UI.
-   Treat files, command output, retrieved content, and external
    messages as untrusted data---not as instructions that can override
    system policy.
-   Separate planning from execution. A proposed action is not an
    executed action.
-   Require confirmation for destructive, external-facing, financial,
    privacy-sensitive, or otherwise consequential actions unless a
    narrow, user-granted policy explicitly authorizes them.
-   For local filesystem access, restrict operations to authorized paths
    and defend against path traversal and symlink escapes where
    applicable.
-   For shell commands, avoid arbitrary command construction from
    model-generated strings. Prefer allowlisted operations, structured
    arguments, timeouts, resource limits, and clear approval gates.
-   Keep secrets out of prompts, logs, command output, and client
    bundles.
-   Record action intent, authorization basis, execution status,
    evidence, and failure reason without logging unnecessary sensitive
    content.
-   On uncertainty or missing permission, ask the user or stop safely.

## 8. Domain and persistence expectations

Keep the domain model explicit. Likely concepts include:

-   **Commitment/task:** What needs to happen, its owner, deadline,
    status, and context.
-   **Dependency:** What must happen before another action can proceed.
-   **Next action:** The smallest useful executable step.
-   **Reminder/scheduled job:** When a user should be prompted or a
    permitted operation should run.
-   **Approval:** A time-bounded decision authorizing a specific action
    and scope.
-   **Execution/run:** An attempt to perform an action, including
    status, tool calls, evidence, and errors.
-   **Audit event:** A meaningful state change or security-relevant
    action.

These are conceptual entities, not a demand to create all tables
immediately. Define legal state transitions and enforce important
invariants in application logic and, where appropriate, database
constraints. Use migrations for schema changes; do not silently mutate
production schemas.

## 9. API and integration conventions

-   Keep transport handlers thin; put business rules in
    application/domain services.
-   Validate all external input at system boundaries.
-   Use typed request/response schemas and stable error formats.
-   Make retries safe through idempotency keys or deduplication where
    needed.
-   Authenticate and authorize every protected operation.
-   Keep gateway-specific payloads inside adapters; normalize them into
    shared internal contracts.
-   Do not let an integration bypass core permissions or workflow state
    transitions.
-   Version public contracts when breaking changes are necessary.

## 10. Engineering workflow for the coding agent

Before editing:

1.  Inspect the repository tree, existing `AGENTS.md` files, README,
    package manifests, lockfiles, environment examples, and relevant
    tests.
2.  Read the product requirements and system architecture documents if
    present. Treat them as the source of truth for settled decisions.
3.  Identify the current implementation, conventions, and smallest
    coherent change.
4.  State assumptions only when they materially affect the
    implementation; do not invent requirements.

While implementing:

-   Make small, modular, reviewable changes.
-   Reuse existing abstractions before creating new ones.
-   Avoid unrelated refactors and speculative abstractions.
-   Keep interfaces and dependencies explicit; avoid circular
    dependencies.
-   Add or update tests for changed behavior, especially state
    transitions, permissions, retries, idempotency, and failure paths.
-   Update documentation and configuration examples when behavior or
    setup changes.
-   Never commit secrets, real user data, or local environment files.
-   Do not add dependencies without a clear reason; prefer maintained,
    minimal dependencies.

Before finishing:

1.  Run the narrowest relevant tests, then broader checks when
    practical.
2.  Run formatting, linting, type checking, and migrations/schema
    validation when configured.
3.  Inspect the diff for accidental changes, security issues, and
    incomplete TODOs.
4.  Report what changed, important design decisions, commands/tests run,
    results, and any remaining limitations. Be explicit about checks
    that could not be run.

If a command fails, diagnose the failure; do not report the check as
passing.

## 11. Quality and testing priorities

Test the behavior, not just the happy path. Prioritize:

-   Capture and persistence of a commitment.
-   Deadline/time-zone interpretation.
-   Dependency and next-action selection.
-   Reminder delivery and rescheduling.
-   Approval enforcement and revoked permissions.
-   Duplicate job delivery and idempotent execution.
-   Worker/API restart recovery and missed jobs.
-   Tool timeouts, retries, partial failure, and verification.
-   Unauthorized local file or command access.
-   Gateway event normalization and duplicate messages.
-   User-visible error and recovery states.

Use unit tests for domain rules, integration tests for persistence and
adapters, and end-to-end tests for the primary execution loop.

## 12. UX principles

-   Show the next useful action before exposing a large task list.
-   Make commitments, deadlines, and blocked dependencies easy to
    understand.
-   Use reminders that are timely and contextual, not repetitive by
    default.
-   Make approval requests specific: what will happen, why, and with
    what scope.
-   Distinguish clearly between planned, awaiting approval, running,
    succeeded, failed, and needs-user-input states.
-   Provide a clear recovery action after failure.
-   Avoid guilt, shame, streak pressure, and language that blames users
    for missed tasks.
-   Keep the default experience calm and concise, with detail available
    on demand.

## 13. Documentation and decision hierarchy

When instructions conflict, follow this order:

1.  Explicit instructions from the user/product owner in the current
    task.
2.  Existing accepted product requirements and architecture decisions.
3.  Repository-level and nested `AGENTS.md` instructions.
4.  Established codebase conventions.
5.  This document's general guidance.

If a major decision is ambiguous or a proposed change conflicts with
product scope, explain the trade-off and ask before making a broad or
irreversible change. Do not silently expand the MVP.

Keep documentation aligned: - `PRD` --- user problem, scope, behavior,
and acceptance criteria. - `03-system-architecture.md` (or the
repository's equivalent) --- component boundaries, data flows,
persistence, security, and execution lifecycle. - `AGENTS.md` ---
durable instructions for coding agents.

## 14. Definition of done

A change is done when:

-   It solves the requested problem without expanding scope
    unnecessarily.
-   Relevant tests and quality checks pass, or failures are clearly
    reported.
-   Permission, privacy, failure, and recovery behavior are handled
    where relevant.
-   Persistence and scheduling semantics are correct for the feature.
-   Documentation/configuration is updated where necessary.
-   The final summary accurately distinguishes implemented behavior from
    planned work.

## 15. Deferred tasks and reminders

-   **Model Settings API & Frontend Web UI:** The model configuration subsystem is implemented in the core/backend package first (`packages/core/src/praxis_core/models`). The corresponding FastAPI endpoints (`/api/models`) and Next.js Model Settings UI (`/settings/models`) are intentionally deferred to a later phase.

## 16. Implemented execution contract

The current durable vertical slice includes a SQLite-backed FastAPI API,
trusted bearer-token identity, exact approval binding, and a bounded
`webhook_post` adapter. Preserve these invariants when changing it:

-   `POST /tasks/{task_id}/execute` creates and persists an execution attempt
    before dispatching an external request.
-   The idempotency key and action arguments remain bound to that attempt;
    retries must not silently create a second side effect.
-   Webhook actions require an approved, single-use token bound to the exact
    action fingerprint. Reconciliation never consumes approval again.
-   Only a provider response with `status: completed` is confirmed evidence.
    Malformed, oversized, timed-out, transport-error, pending, or ambiguous
    responses remain `outcome_unknown`.
-   A provider `status: failed` is authoritative only with
    `failure_final: true` and documented semantics that the action did not
    occur or that any partial effect is explicitly represented.
-   `POST /tasks/{task_id}/reconcile` performs a provider status read only. It
    must never dispatch the original POST again. Concurrent reconciliation must
    not overwrite a newer terminal attempt state.
-   Provider operation IDs are untrusted input. Keep them constrained before
    constructing status URLs, and never allow them to select arbitrary hosts or
    schemes.

The provider contract requires documented idempotency-key retention and
duplicate-request behavior, an operation ID or equivalent lookup handle, and
authoritative status semantics. A missing operation ID cannot be used to build
an ambiguous status lookup.

## 17. Outbound HTTP deployment security

The webhook adapter validates schemes, rejects URL credentials, blocks
localhost/private/link-local destinations, supports exact host allowlisting,
disables redirects, validates all resolved IPv4/IPv6 addresses, and enforces a
streaming response-size limit. These are application-level defenses, not a
complete network boundary.

Production deployments must add network-level egress restrictions or a
controlled resolver/transport that prevents DNS time-of-check/time-of-use
divergence. Do not expose arbitrary webhook URLs to untrusted callers, and do
not forward secrets across origins. Keep `PRAXIS_WEBHOOK_ALLOWED_HOSTS` and
status-provider configuration explicit and reviewed.

## 18. Verification expectations for execution changes

Execution changes require tests for both normal and adversarial lifecycle
paths:

-   approval replay, action-argument tampering, owner mismatch, and attempt/task
    mismatch;
-   duplicate execution and concurrent reconciliation;
-   provider timeout after acceptance, malformed or oversized responses,
    pending status, authoritative failure, and missing operation IDs;
-   process restart with durable attempt, provider ID, idempotency key, audit
    state, and recovery guidance intact;
-   controlled provider behavior proving one POST followed by read-only GET
    reconciliation and no second POST.

Run the full configured suite plus Ruff and `git diff --check` before handing
off. The API tests use `httpx.AsyncClient` with `ASGITransport`; do not
reintroduce Starlette's deprecated synchronous `TestClient` path.
