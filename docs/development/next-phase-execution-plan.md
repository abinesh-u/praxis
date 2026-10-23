# Praxis next-phase execution plan

This is the right direction for the next phase of your personal AI execution system. With the durable execution loop committed and pushed, the priority should shift from proving the architecture in controlled tests to proving that it behaves safely under real operational conditions.

I would preserve your eight workstreams, but tighten their dependencies and acceptance gates. The critical path is:

**Real provider → recovery guarantees → release readiness → API hardening → minimal web UI → durable scheduler → Telegram gateway → evidence-based PostgreSQL decision.**

One important distinction: a successful simulated provider test proves your recovery logic works against the harness. It does not yet prove that the real provider honors idempotency, exposes reliable operation status, or behaves correctly during ambiguous network failures.

## Recommended execution plan

I would organize the next phase into six gated milestones. This keeps your existing architecture intact and prevents downstream work from being built on unverified execution guarantees.

### M1 — Real-provider validation

- Deploy against a disposable, idempotency-capable provider.
- Verify credentials, TLS, DNS, outbound network restrictions, timeouts, and status lookup.
- Test acceptance followed by a lost response, ensuring reconciliation never blindly redispatches an ambiguous operation.

**Exit gate:** documented provider contract, repeatable integration tests, and evidence that timeout recovery does not create duplicate provider effects.

### M2 — Recovery and release readiness

- Define missing operation-ID and permanently pending policies.
- Document operator procedures for unresolved attempts.
- Test SQLite backup and restore.
- Verify audit retention, secret-safe logs, deployment authentication, and owner isolation.
- Document configuration and build a deployment smoke test.

**Exit gate:** an operator can diagnose, recover, or safely escalate an unresolved execution without risking an uncontrolled repeat.

### M3 — Persistence and concurrency

- Introduce explicit schema migrations and version tracking.
- Strengthen concurrent execution, approval, and reconciliation tests.
- Bound attempt-history queries and define retention policies.
- Test process restarts while requests are active.

**Exit gate:** state transitions remain correct under concurrency and restart; persistence behavior is portable across database implementations.

### M4 — Minimal operational web UI

Implement only six screens or workflows:

1. Today view
2. Capture task
3. Approval review
4. Execution status
5. Outcome-unknown recovery
6. Evidence and task detail

**Exit gate:** every workflow uses the existing application services and API contracts. The UI never implements an independent execution path.

### M5 — Durable scheduling and reminders

- Persist scheduled jobs and define job-claiming semantics.
- Handle time zones, daylight-saving transitions, and missed runs.
- Add duplicate-delivery protection, retry/backoff, and delivery audit.
- Recover safely after worker restarts.

**Exit gate:** jobs survive restarts, competing workers cannot claim the same execution incorrectly, and reminder delivery outcomes are auditable.

### M6 — Telegram gateway and database decision

- Normalize Telegram updates into shared application commands.
- Authenticate users, enforce ownership, and deduplicate webhook events.
- Route commands through the same services used by CLI and web.
- Evaluate PostgreSQL only against measured deployment, concurrency, and operational requirements.

**Exit gate:** Telegram is another transport adapter, not a second business-logic implementation. The database choice follows evidence rather than anticipated scale alone.

## Three architectural rules to preserve

These matter more than the number of features shipped.

1. **Ambiguous execution is a first-class state.** A timeout is not proof of failure. If the provider may have accepted an operation, reconcile using the provider's documented idempotency and status semantics before considering another dispatch.
2. **All transports share the same application layer.** CLI, web, and Telegram should call the same task, approval, execution, and recovery services. Authorization remains enforced at the application boundary.
3. **Persistence portability must preserve domain behavior.** SQLite-to-PostgreSQL migration should change storage mechanics, not execution state transitions, ownership rules, audit semantics, or idempotency guarantees.

Your existing baseline is a strong starting point: the deterministic provider harness has validated timeout recovery, SQLite-backed API reconstruction, and reconciliation, with 202 tests passing. That is a meaningful checkpoint, but real-provider behavior and deployment-level security remain unproven.

## What to implement next

Start with M1, and do not start the scheduler or web UI yet. Make the next coding-agent task narrowly scoped to real-provider deployment validation.

The deliverable should contain:

- A provider contract documenting idempotency-key scope, retention, operation lookup, terminal states, and retry semantics.
- An isolated deployment configuration with restricted credentials and outbound access.
- An integration-test matrix covering accepted requests, rejected requests, timeouts, delayed status visibility, and provider lookup failures.
- Assertions proving that ambiguous attempts are not blindly redispatched.
- A reproducible validation report with evidence, failure conditions, and explicit limitations.

One critical caveat: no generic client-side implementation can guarantee exactly-once external effects if the provider does not supply sufficient idempotency or reconciliation guarantees. The system should preserve `outcome_unknown` and escalate rather than manufacture certainty.

The immediate objective is to establish the real provider as a trustworthy execution boundary. Once that gate passes, the remaining work can build on verified operational guarantees rather than assumptions.
